"""
Local VM API for admin + generation proxy.

This service runs behind nginx at same-origin `/api/*` and is used by the
frontend to avoid browser CORS/cookie issues with direct cross-origin Modal
calls. It only routes generation through explicitly configured ready accounts.
"""
from __future__ import annotations

# Load .env before anything reads os.environ
from pathlib import Path as _Path
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_Path(__file__).resolve().parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed (e.g. in Modal container) - skip

import asyncio
import logging
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger("admin_local")

# Rough A10G cost estimates for spending guard
_VIDEO_COST_USD = float(os.environ.get("VIDEO_COST_USD_ESTIMATE", "0.05"))   # ~2.7min A10G
_IMAGE_COST_USD = float(os.environ.get("IMAGE_COST_USD_ESTIMATE", "0.015"))  # ~0.8min A10G
_VALID_WARMUP_MODELS = ("anisora", "phr00t", "pony", "flux")
_DEFAULT_ADMIN_WARMUP_MODELS = tuple(
    m.strip().lower()
    for m in os.environ.get("WARMUP_DEFAULT_MODELS", "pony,flux").split(",")
    if m.strip().lower() in _VALID_WARMUP_MODELS
) or ("pony", "flux")
WARMUP_TTL_SECONDS = max(300, int(os.environ.get("WARMUP_TTL_SECONDS", "21600")))
WARMUP_COOLDOWN_SECONDS = max(0, int(os.environ.get("WARMUP_COOLDOWN_SECONDS", "3600")))

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from cryptography.fernet import Fernet

import accounts as acc_store
import storage
from admin_security import (
    ADMIN_IDLE_TIMEOUT_SECONDS,
    ADMIN_SESSION_COOKIE,
    _ensure_audit_table,
    get_admin_auth,
    verify_admin_key_header,
    verify_admin_login_password,
)
from auth import GENERATION_SESSION_COOKIE, verify_generation_session
from config import DEFAULT_PAGE_SIZE
from deployer import (
    deploy_account_async,
    deploy_all_accounts,
    get_missing_shared_env_keys,
    required_shared_env_keys,
    trigger_workspace_warmup_detailed,
)
from router import MAX_FALLBACKS, NoReadyAccountError, router as account_router
from schemas import (
    AdminLoginRequest,
    AdminSessionStateResponse,
    DeleteResponse,
    GalleryItemResponse,
    GalleryResponse,
    GenerateRequest,
    GenerateResponse,
    GenerationSessionStateResponse,
    TaskStatus,
)


_TRANSIENT_REMOTE_STATUS_CODES = {429, 500, 502, 503, 504}
_SHARED_ENV_KEYS = required_shared_env_keys()
_PBKDF2_RE = re.compile(r"^pbkdf2_sha256\$(\d+)\$([^$]+)\$([0-9a-fA-F]+)$")
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
_STALE_SWEEP_INTERVAL_SECONDS = max(30, int(os.environ.get("STALE_SWEEP_INTERVAL_SECONDS", "60")))
_PENDING_TIMEOUT_SECONDS = max(30, int(os.environ.get("PENDING_TASK_TIMEOUT_SECONDS", "180")))
_PROCESSING_TIMEOUT_SECONDS = max(120, int(os.environ.get("PROCESSING_TASK_TIMEOUT_SECONDS", "900")))
_INSTANCE_LOCK_ENABLED = os.environ.get("ENFORCE_SINGLE_INSTANCE", "1").strip() in {"1", "true", "yes", "on"}
_INSTANCE_LOCK_NAME = (os.environ.get("ADMIN_LOCAL_LOCK_NAME", "admin_local") or "admin_local").strip()
_INSTANCE_LOCK_LEASE_SECONDS = max(30, int(os.environ.get("ADMIN_LOCAL_LOCK_LEASE_SECONDS", "90")))
_INSTANCE_LOCK_HEARTBEAT_SECONDS = max(10, int(os.environ.get("ADMIN_LOCAL_LOCK_HEARTBEAT_SECONDS", "25")))
_INSTANCE_OWNER_ID = str(uuid.uuid4())
_LOCAL_FALLBACK_WORKSPACE = "__local_fallback__"
_instance_lock_acquired = False


def _error_payload(*, code: str, detail: str, user_action: str) -> dict:
    return {"code": code, "detail": detail, "user_action": user_action}


def _parse_warmup_mode(raw_mode: Any) -> str:
    mode = str(raw_mode or "best_effort").strip().lower()
    if mode not in {"required", "best_effort"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                code="validation_error",
                detail="Warmup mode must be 'required' or 'best_effort'.",
                user_action="Fix warmup mode and retry.",
            ),
        )
    return mode


def _parse_warmup_models(raw_models: Any) -> list[str]:
    if raw_models is None:
        return list(_DEFAULT_ADMIN_WARMUP_MODELS)
    if not isinstance(raw_models, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                code="validation_error",
                detail="Warmup models must be an array of model ids.",
                user_action="Provide at least one valid model id.",
            ),
        )
    parsed = []
    for item in raw_models:
        model = str(item).strip().lower()
        if model not in _VALID_WARMUP_MODELS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_error_payload(
                    code="validation_error",
                    detail=f"Unsupported warmup model: {item}",
                    user_action="Use one of: anisora, phr00t, pony, flux.",
                ),
            )
        if model not in parsed:
            parsed.append(model)
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                code="validation_error",
                detail="Warmup models list cannot be empty.",
                user_action="Provide at least one valid model id.",
            ),
        )
    return parsed


def _parse_positive_int(raw_value: Any, default_value: int, field_name: str) -> int:
    if raw_value is None:
        return default_value
    try:
        value = int(raw_value)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                code="validation_error",
                detail=f"{field_name} must be an integer.",
                user_action="Provide a valid integer and retry.",
            ),
        )
    if value < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                code="validation_error",
                detail=f"{field_name} cannot be negative.",
                user_action="Provide a value >= 0 and retry.",
            ),
        )
    return value


def _normalize_request_dict(req: GenerateRequest) -> dict:
    req_dict = req.model_dump()
    req_dict["model"] = req.model.value
    req_dict["type"] = req.type.value
    model_key = req_dict["model"]
    if model_key == "anisora" and req_dict.get("steps") is None:
        req_dict["steps"] = 8
    if model_key == "phr00t":
        if req_dict.get("steps") is None:
            req_dict["steps"] = 4
        if req_dict.get("cfg_scale") is None and req_dict.get("guidance_scale") is not None:
            req_dict["cfg_scale"] = req_dict["guidance_scale"]
        if req_dict.get("cfg_scale") is None:
            req_dict["cfg_scale"] = 1.0
    return req_dict


def _build_remote_base(workspace: str, remote_base_url: Optional[str] = None) -> str:
    ws = workspace.strip()
    if not ws:
        raise ValueError("workspace is empty")
    if ws == _LOCAL_FALLBACK_WORKSPACE:
        local_base = (os.environ.get("LOCAL_FALLBACK_BASE_URL") or "").strip().rstrip("/")
        if not local_base:
            raise ValueError("local fallback base is empty")
        return local_base
    direct_base = (remote_base_url or "").strip().rstrip("/")
    if direct_base:
        return direct_base
    by_workspace = acc_store.get_account_by_workspace(ws)
    stored_base = str((by_workspace or {}).get("remote_base_url") or "").strip().rstrip("/")
    if stored_base:
        return stored_base
    return f"https://{ws}--gooni-api.modal.run"


def _validate_admin_password_hash(raw_hash: str) -> Optional[str]:
    value = (raw_hash or "").strip()
    if not value:
        return "ADMIN_PASSWORD_HASH is empty"
    pbkdf2_match = _PBKDF2_RE.match(value)
    if pbkdf2_match:
        iterations = int(pbkdf2_match.group(1))
        digest = pbkdf2_match.group(3)
        if iterations < 100_000 or iterations > 10_000_000:
            return "ADMIN_PASSWORD_HASH has invalid PBKDF2 iterations"
        if len(digest) < 32:
            return "ADMIN_PASSWORD_HASH digest is too short"
        return None
    if value.startswith(_BCRYPT_PREFIXES):
        if len(value) < 59:
            return "ADMIN_PASSWORD_HASH bcrypt value is too short"
        return None
    return "ADMIN_PASSWORD_HASH must be pbkdf2_sha256$... or bcrypt"


def _validate_accounts_encrypt_key(raw_key: str) -> Optional[str]:
    value = (raw_key or "").strip()
    if not value:
        return "ACCOUNTS_ENCRYPT_KEY is empty"
    try:
        Fernet(value.encode("utf-8"))
    except Exception:
        return "ACCOUNTS_ENCRYPT_KEY is not a valid Fernet key"
    return None


def _validate_shared_env_values() -> tuple[dict[str, Any], list[str]]:
    status_by_key: dict[str, Any] = {}
    errors: list[str] = []
    for key in _SHARED_ENV_KEYS:
        value = (os.environ.get(key) or "").strip()
        key_item: dict[str, Any] = {"status": "ok" if value else "missing"}
        if not value:
            status_by_key[key] = key_item
            continue

        validation_error: Optional[str] = None
        if key == "API_KEY" and len(value) < 16:
            validation_error = "API_KEY must be at least 16 characters"
        elif key == "ADMIN_LOGIN" and len(value) < 3:
            validation_error = "ADMIN_LOGIN must be at least 3 characters"
        elif key == "ADMIN_PASSWORD_HASH":
            validation_error = _validate_admin_password_hash(value)
        elif key == "ACCOUNTS_ENCRYPT_KEY":
            validation_error = _validate_accounts_encrypt_key(value)
        elif key == "HF_TOKEN" and len(value) < 10:
            validation_error = "HF_TOKEN looks too short"

        if validation_error:
            key_item["status"] = "invalid"
            key_item["message"] = validation_error
            errors.append(validation_error)
        status_by_key[key] = key_item
    return status_by_key, errors


def _shared_env_requirements_payload() -> dict[str, Any]:
    missing = get_missing_shared_env_keys()
    by_key, errors = _validate_shared_env_values()
    modal_cli = _check_modal_cli()
    checks = {
        "env": {
            "status": "ok" if len(missing) == 0 and len(errors) == 0 else "fail",
            "missing": list(missing),
            "invalid": list(errors),
        },
        "admin_hash": by_key.get("ADMIN_PASSWORD_HASH", {"status": "missing"}),
        "accounts_encrypt_key": by_key.get("ACCOUNTS_ENCRYPT_KEY", {"status": "missing"}),
        "modal_cli": modal_cli,
    }
    categories: list[dict[str, str]] = []
    if missing:
        categories.append(
            {
                "code": "missing_shared_env",
                "detail": "Required shared environment variables are missing.",
                "user_action": "Set API_KEY, ADMIN_LOGIN, ADMIN_PASSWORD_HASH, ACCOUNTS_ENCRYPT_KEY, HF_TOKEN and restart.",
            }
        )
    if errors:
        categories.append(
            {
                "code": "invalid_shared_env",
                "detail": "Some shared environment values are invalid.",
                "user_action": "Fix invalid env values and retry.",
            }
        )
    if modal_cli["status"] != "ok":
        categories.append(
            {
                "code": "modal_cli_unavailable",
                "detail": str(modal_cli.get("message") or "Modal CLI is unavailable."),
                "user_action": "Install Modal CLI in runtime (python -m modal --version must work) and retry.",
            }
        )
    return {
        "ready": len(categories) == 0,
        "required_env": by_key,
        "missing_env": missing,
        "validation_errors": errors,
        "checks": checks,
        "categories": categories,
    }


def _check_modal_cli() -> dict[str, str]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "modal", "--version"],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        return {"status": "fail", "message": f"python -m modal --version failed: {exc}"}
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown error").strip()
        return {"status": "fail", "message": err[:240]}
    version = (result.stdout or "").strip() or "ok"
    return {"status": "ok", "version": version[:120]}


def _require_api_key() -> str:
    value = (os.environ.get("API_KEY") or "").strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_payload(
                code="server_misconfigured",
                detail="API_KEY is missing in VM runtime.",
                user_action="Set API_KEY in VM env and restart container.",
            ),
        )
    return value


def _split_remote_task_id(task_id: str) -> tuple[str, str]:
    if "::" not in task_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                code="invalid_task_id",
                detail="Expected composite task id in format workspace::task_id.",
                user_action="Use task id returned by /generate and retry.",
            ),
        )
    workspace, remote_task_id = task_id.split("::", 1)
    if not workspace.strip() or not remote_task_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                code="invalid_task_id",
                detail="Composite task id is malformed.",
                user_action="Use task id returned by /generate and retry.",
            ),
        )
    return workspace.strip(), remote_task_id.strip()


async def _proxy_status_json(workspace: str, remote_task_id: str, api_key: str) -> dict[str, Any]:
    timeout = httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=5.0)
    last_error = "unknown remote status error"
    for attempt in range(3):
        base = _build_remote_base(workspace)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    f"{base}/status/{remote_task_id}",
                    headers={"X-API-Key": api_key},
                )
            if resp.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=_error_payload(
                        code="task_not_found",
                        detail="Remote task not found.",
                        user_action="Verify task id and retry.",
                    ),
                )
            if resp.status_code >= 400:
                last_error = f"remote_{resp.status_code}:{resp.text[:200]}"
                if resp.status_code in _TRANSIENT_REMOTE_STATUS_CODES and attempt < 2:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                raise RuntimeError(last_error)
            payload = resp.json()
            if isinstance(payload, dict):
                payload["task_id"] = f"{workspace}::{remote_task_id}"
                if str(payload.get("status") or "") == "done":
                    payload["result_url"] = f"/api/results/{workspace}::{remote_task_id}"
                    if payload.get("preview_url"):
                        payload["preview_url"] = f"/api/preview/{workspace}::{remote_task_id}"
            return payload
        except HTTPException:
            raise
        except Exception as exc:
            last_error = str(exc)
            if attempt < 2:
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            raise HTTPException(
                status_code=502,
                detail=_error_payload(
                    code="remote_status_unavailable",
                    detail=f"Remote status fetch failed: {last_error}",
                    user_action="Retry shortly.",
                ),
            ) from exc
    raise HTTPException(
        status_code=502,
        detail=_error_payload(
            code="remote_status_unavailable",
            detail=f"Remote status fetch failed: {last_error}",
            user_action="Retry shortly.",
        ),
    )


async def _proxy_binary(workspace: str, remote_task_id: str, path: str, api_key: str, *, read_timeout: float) -> Response:
    timeout = httpx.Timeout(connect=5.0, read=read_timeout, write=30.0, pool=5.0)
    last_error = "unknown remote stream error"
    for attempt in range(3):
        client = httpx.AsyncClient(timeout=timeout)
        response: Optional[httpx.Response] = None
        try:
            base = _build_remote_base(workspace)
            request = client.build_request(
                "GET",
                f"{base}/{path}/{remote_task_id}",
                headers={"X-API-Key": api_key},
            )
            response = await client.send(request, stream=True)
            if response.status_code == 404:
                await response.aclose()
                await client.aclose()
                code = "result_not_found" if path == "results" else "preview_not_found"
                raise HTTPException(
                    status_code=404,
                    detail=_error_payload(
                        code=code,
                        detail=f"Remote {path[:-1]} not found.",
                        user_action="Verify task id or regenerate.",
                    ),
                )
            if response.status_code >= 400:
                payload = (await response.aread()).decode(errors="ignore")
                last_error = f"remote_{response.status_code}:{payload[:200]}"
                await response.aclose()
                await client.aclose()
                if response.status_code in _TRANSIENT_REMOTE_STATUS_CODES and attempt < 2:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                raise RuntimeError(last_error)

            media_type = response.headers.get("content-type", "application/octet-stream")

            async def _iter_bytes():
                try:
                    async for chunk in response.aiter_bytes():
                        yield chunk
                finally:
                    await response.aclose()
                    await client.aclose()

            return StreamingResponse(_iter_bytes(), media_type=media_type)
        except HTTPException:
            if response is not None:
                await response.aclose()
            await client.aclose()
            raise
        except Exception as exc:
            if response is not None:
                await response.aclose()
            await client.aclose()
            last_error = str(exc)
            if attempt < 2:
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            code = "remote_result_unavailable" if path == "results" else "remote_preview_unavailable"
            raise HTTPException(
                status_code=502,
                detail=_error_payload(
                    code=code,
                    detail=f"Remote {path} fetch failed: {last_error}",
                    user_action="Retry shortly.",
                ),
            ) from exc

    code = "remote_result_unavailable" if path == "results" else "remote_preview_unavailable"
    raise HTTPException(
        status_code=502,
        detail=_error_payload(
            code=code,
            detail=f"Remote {path} fetch failed: {last_error}",
            user_action="Retry shortly.",
        ),
    )


def _is_retryable_remote_error(exc: Exception) -> bool:
    text = str(exc).lower()
    # Retry on explicit remote failures and infra/network errors.
    return (
        "remote_429" in text
        or "remote_5" in text
        or "timeout" in text
        or "connection" in text
        or "network" in text
        or "workspace is empty" in text
        or "workspace_not_configured" in text
    )


async def _dispatch_local_fallback(req_payload: dict[str, Any], req_type: str, last_error: str) -> GenerateResponse:
    """
    Optional local fallback runner.

    Set LOCAL_FALLBACK_BASE_URL to a reachable API endpoint that supports
    POST /generate_direct with the same payload contract.
    """
    local_base = (os.environ.get("LOCAL_FALLBACK_BASE_URL") or "").strip().rstrip("/")
    if not local_base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_payload(
                code="local_fallback_unavailable",
                detail=f"Remote dispatch failed and local fallback is not configured. Last error: {last_error}",
                user_action="Set LOCAL_FALLBACK_BASE_URL or restore ready Modal accounts.",
            ),
        )

    local_api_key = (os.environ.get("LOCAL_FALLBACK_API_KEY") or os.environ.get("API_KEY") or "").strip()
    headers = {"X-API-Key": local_api_key} if local_api_key else {}
    timeout = httpx.Timeout(connect=4.0, read=60.0, write=60.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{local_base}/generate_direct", json=req_payload, headers=headers)
        if resp.status_code == 422:
            payload = {}
            try:
                payload = resp.json()
            except Exception:
                payload = {}
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
            if isinstance(detail, dict) and {"code", "detail", "user_action"}.issubset(detail):
                raise HTTPException(status_code=422, detail=detail)
            raise HTTPException(
                status_code=422,
                detail=_error_payload(
                    code="validation_error",
                    detail="Validation failed.",
                    user_action="Fix request fields and retry.",
                ),
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"local_{resp.status_code}:{resp.text[:200]}")
        data = resp.json()
        local_task_id = str(data.get("task_id") or "").strip()
        if not local_task_id:
            raise RuntimeError("local fallback response missing task_id")
        composite_task_id = f"{_LOCAL_FALLBACK_WORKSPACE}::{local_task_id}"
        logger.info("local_fallback_dispatch_success type=%s task_id=%s", req_type, composite_task_id)
        return GenerateResponse(task_id=composite_task_id, status=TaskStatus.pending)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_payload(
                code="local_fallback_unavailable",
                detail=f"Remote dispatch failed and local fallback failed: {exc}",
                user_action="Restore ready Modal accounts or verify LOCAL_FALLBACK_BASE_URL.",
            ),
        ) from exc


admin_idle_timeout_seconds = int(os.environ.get("ADMIN_IDLE_TIMEOUT_SECONDS", str(ADMIN_IDLE_TIMEOUT_SECONDS)))
generation_ttl_seconds = int(os.environ.get("GENERATION_SESSION_TTL_SECONDS", str(24 * 3600)))
admin_cookie_secure = os.environ.get("ADMIN_COOKIE_SECURE", "0") == "1"
admin_cookie_samesite = (os.environ.get("ADMIN_COOKIE_SAMESITE", "lax") or "lax").lower()
if admin_cookie_samesite not in {"none", "lax", "strict"}:
    admin_cookie_samesite = "lax"
if admin_cookie_samesite == "none" and not admin_cookie_secure:
    admin_cookie_samesite = "lax"

api = FastAPI(
    title="Gooni Local API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)


def _set_session_cookie(response: Response, key: str, value: str, max_age: int) -> None:
    response.set_cookie(
        key=key,
        value=value,
        max_age=max_age,
        httponly=True,
        secure=admin_cookie_secure,
        samesite=admin_cookie_samesite,
        path="/",
    )


def _delete_session_cookie(response: Response, key: str) -> None:
    response.delete_cookie(
        key=key,
        httponly=True,
        secure=admin_cookie_secure,
        samesite=admin_cookie_samesite,
        path="/",
    )


async def _recovery_loop() -> None:
    """Periodically recover failed accounts regardless of traffic."""
    from router import FAILED_ACCOUNT_COOLDOWN_SECONDS
    while True:
        try:
            await asyncio.sleep(60)
            recovered = acc_store.recover_failed_accounts(
                cooldown_seconds=FAILED_ACCOUNT_COOLDOWN_SECONDS
            )
            if recovered:
                logger.info("background_recovery recovered=%s", recovered)
        except Exception:
            logger.exception("background_recovery_error")


async def _maintenance_loop() -> None:
    """Periodically fail stale tasks and clean up expired artifacts."""
    while True:
        try:
            await asyncio.sleep(_STALE_SWEEP_INTERVAL_SECONDS)
            stale = storage.mark_stale_tasks_failed(
                pending_timeout_seconds=_PENDING_TIMEOUT_SECONDS,
                processing_timeout_seconds=_PROCESSING_TIMEOUT_SECONDS,
            )
            cleaned = storage.cleanup_expired_artifacts()
            if stale or cleaned:
                logger.info(
                    "maintenance_sweep stale_failed=%s expired_cleaned=%s",
                    stale,
                    cleaned,
                )
        except Exception:
            logger.exception("maintenance_sweep_error")


async def _instance_lock_heartbeat_loop() -> None:
    while True:
        try:
            await asyncio.sleep(_INSTANCE_LOCK_HEARTBEAT_SECONDS)
            if not _instance_lock_acquired:
                continue
            still_owned = storage.refresh_instance_lock(_INSTANCE_LOCK_NAME, _INSTANCE_OWNER_ID)
            if not still_owned:
                logger.critical("runtime_instance_lock_lost lock=%s", _INSTANCE_LOCK_NAME)
        except Exception:
            logger.exception("runtime_instance_lock_heartbeat_error")


@api.on_event("startup")
async def _startup() -> None:
    global _instance_lock_acquired
    os.makedirs("/results", exist_ok=True)
    storage.init_db()
    if _INSTANCE_LOCK_ENABLED:
        acquired, owner = storage.acquire_instance_lock(
            _INSTANCE_LOCK_NAME,
            _INSTANCE_OWNER_ID,
            lease_seconds=_INSTANCE_LOCK_LEASE_SECONDS,
        )
        if not acquired:
            raise RuntimeError(
                f"Another instance is already active (lock={_INSTANCE_LOCK_NAME}, owner={owner}). "
                "Stop the other instance or disable ENFORCE_SINGLE_INSTANCE."
            )
        _instance_lock_acquired = True
    acc_store.init_accounts_table()
    _ensure_audit_table()
    asyncio.create_task(_recovery_loop())
    asyncio.create_task(_maintenance_loop())
    if _INSTANCE_LOCK_ENABLED:
        asyncio.create_task(_instance_lock_heartbeat_loop())


@api.on_event("shutdown")
async def _shutdown() -> None:
    global _instance_lock_acquired
    if _instance_lock_acquired:
        try:
            storage.release_instance_lock(_INSTANCE_LOCK_NAME, _INSTANCE_OWNER_ID)
        finally:
            _instance_lock_acquired = False


@api.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@api.post("/auth/session", status_code=status.HTTP_204_NO_CONTENT)
async def create_generation_session(response: Response, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    token, _ = storage.create_generation_session(
        ttl_seconds=generation_ttl_seconds,
        client_context=client_ip,
    )
    _set_session_cookie(response, GENERATION_SESSION_COOKIE, token, generation_ttl_seconds)
    return None


@api.get("/auth/session", response_model=GenerationSessionStateResponse)
async def get_generation_session_state(request: Request):
    token = request.cookies.get(GENERATION_SESSION_COOKIE, "")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error_payload(
                code="generation_session_missing",
                detail="Generation session is missing.",
                user_action="Create a new session and retry.",
            ),
        )
    active, reason, expires_at = storage.validate_generation_session(token)
    if not active:
        code = "generation_session_expired" if reason == "expired" else "generation_session_invalid"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error_payload(
                code=code,
                detail="Generation session is invalid or expired.",
                user_action="Create a new session and retry.",
            ),
        )
    return GenerationSessionStateResponse(valid=True, active=True, expires_at=expires_at)


@api.delete("/auth/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_generation_session(response: Response, request: Request):
    token = request.cookies.get(GENERATION_SESSION_COOKIE, "")
    if token:
        storage.revoke_generation_session(token)
    _delete_session_cookie(response, GENERATION_SESSION_COOKIE)
    return None


@api.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, _: str = Depends(verify_generation_session)):
    api_key = _require_api_key()
    req_payload = _normalize_request_dict(req)

    tried_accounts: list[str] = []
    last_error = "No ready Modal accounts available."
    should_try_local_fallback = False

    for attempt in range(MAX_FALLBACKS + 1):
        try:
            account = account_router.pick() if attempt == 0 else account_router.pick_with_fallback(tried=tried_accounts)
            account_id = str(account["id"])
            tried_accounts.append(account_id)

            workspace = (account.get("workspace") or "").strip()
            if not workspace:
                raise RuntimeError("workspace_not_configured")

            base = _build_remote_base(workspace, str(account.get("remote_base_url") or ""))
            timeout = httpx.Timeout(connect=4.0, read=60.0, write=60.0, pool=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{base}/generate_direct",
                    json=req_payload,
                    headers={"X-API-Key": api_key},
                )

            if resp.status_code == 422:
                payload = {}
                try:
                    payload = resp.json()
                except Exception:
                    payload = {}
                detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
                if isinstance(detail, dict) and {"code", "detail", "user_action"}.issubset(detail):
                    raise HTTPException(status_code=422, detail=detail)
                raise HTTPException(
                    status_code=422,
                    detail=_error_payload(
                        code="validation_error",
                        detail="Validation failed.",
                        user_action="Fix request fields and retry.",
                    ),
                )

            if resp.status_code >= 400:
                raise RuntimeError(f"remote_{resp.status_code}:{resp.text[:200]}")

            data = resp.json()
            remote_task_id = str(data.get("task_id") or "").strip()
            if not remote_task_id:
                raise RuntimeError("remote response missing task_id")

            account_router.mark_success(account_id)
            try:
                gen_type = req_payload.get("type", "")
                cost = _VIDEO_COST_USD if gen_type == "video" else _IMAGE_COST_USD
                acc_store.add_usage(account_id, cost)
            except Exception:
                logger.exception("add_usage_error account_id=%s", account_id)
            return GenerateResponse(task_id=f"{workspace}::{remote_task_id}", status=TaskStatus.pending)

        except HTTPException:
            raise
        except NoReadyAccountError as exc:
            last_error = str(exc)
            should_try_local_fallback = True
            break
        except Exception as exc:
            last_error = str(exc)
            if tried_accounts:
                account_router.mark_failed(tried_accounts[-1], last_error)
            retryable = _is_retryable_remote_error(exc)
            should_try_local_fallback = retryable
            if not retryable:
                break

    if should_try_local_fallback:
        return await _dispatch_local_fallback(req_payload, req_payload.get("type", ""), last_error)

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=_error_payload(
            code="no_ready_accounts",
            detail=f"No ready account could process request. Last error: {last_error}",
            user_action="Open Admin panel, deploy/enable accounts, and retry.",
        ),
    )


@api.get("/status/{task_id}")
async def get_status(task_id: str, _: str = Depends(verify_generation_session)):
    api_key = _require_api_key()
    workspace, remote_task_id = _split_remote_task_id(task_id)
    return await _proxy_status_json(workspace, remote_task_id, api_key)


@api.get("/results/{task_id}")
async def get_result(task_id: str, _: str = Depends(verify_generation_session)):
    api_key = _require_api_key()
    workspace, remote_task_id = _split_remote_task_id(task_id)
    return await _proxy_binary(workspace, remote_task_id, "results", api_key, read_timeout=120.0)


@api.get("/preview/{task_id}")
async def get_preview(task_id: str, _: str = Depends(verify_generation_session)):
    api_key = _require_api_key()
    workspace, remote_task_id = _split_remote_task_id(task_id)
    return await _proxy_binary(workspace, remote_task_id, "preview", api_key, read_timeout=60.0)


@api.get("/gallery", response_model=GalleryResponse)
async def gallery(
    page: int = Query(1, ge=1),
    per_page: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
    sort: str = Query("created_at"),
    model: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    _: str = Depends(verify_generation_session),
):
    api_key = _require_api_key()
    accounts = acc_store.list_ready_accounts()
    if not accounts:
        return GalleryResponse(items=[], total=0, page=page, per_page=per_page, has_more=False)

    merged: list[GalleryItemResponse] = []
    headers = {"X-API-Key": api_key}
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=20.0, pool=5.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for account in accounts:
            workspace = (account.get("workspace") or "").strip()
            if not workspace:
                continue
            try:
                base = _build_remote_base(workspace)
                resp = await client.get(
                    f"{base}/gallery",
                    params={"page": 1, "per_page": 100, "sort": sort, "model": model, "type": type},
                    headers=headers,
                )
                if resp.status_code >= 400:
                    continue
                payload = resp.json()
                for item in payload.get("items", []) if isinstance(payload, dict) else []:
                    remote_id = str(item.get("id") or "").strip()
                    if not remote_id:
                        continue
                    merged.append(
                        GalleryItemResponse(
                            id=f"{workspace}::{remote_id}",
                            model=str(item.get("model") or ""),
                            type=str(item.get("type") or ""),
                            mode=str(item.get("mode") or ""),
                            prompt=str(item.get("prompt") or ""),
                            negative_prompt=str(item.get("negative_prompt") or ""),
                            parameters=item.get("parameters") or {},
                            width=int(item.get("width") or 0),
                            height=int(item.get("height") or 0),
                            seed=int(item.get("seed") or -1),
                            created_at=datetime.fromisoformat(str(item.get("created_at"))),
                            preview_url=f"/api/preview/{workspace}::{remote_id}",
                            result_url=f"/api/results/{workspace}::{remote_id}",
                        )
                    )
            except Exception:
                # Skip unhealthy workspace and continue aggregation.
                continue

    merged.sort(key=lambda x: x.created_at, reverse=True)
    total = len(merged)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = merged[start:end]
    return GalleryResponse(
        items=page_items,
        total=total,
        page=page,
        per_page=per_page,
        has_more=end < total,
    )


@api.delete("/gallery/{task_id}", status_code=status.HTTP_200_OK)
async def delete_gallery_item(task_id: str, _: str = Depends(verify_generation_session)):
    api_key = _require_api_key()
    workspace, remote_task_id = _split_remote_task_id(task_id)

    base = _build_remote_base(workspace)
    timeout = httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.delete(
                f"{base}/gallery/{remote_task_id}",
                headers={"X-API-Key": api_key},
            )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=_error_payload(
                    code="not_found",
                    detail="Gallery item not found.",
                    user_action="Verify item id and retry.",
                ),
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"remote_{resp.status_code}:{resp.text[:200]}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=_error_payload(
                code="remote_gallery_unavailable",
                detail=f"Remote gallery delete failed: {exc}",
                user_action="Retry shortly.",
            ),
        ) from exc
    return DeleteResponse(deleted=True, id=task_id)


@api.post("/admin/login", status_code=status.HTTP_204_NO_CONTENT)
async def admin_login(payload: AdminLoginRequest, request: Request, response: Response):
    verify_admin_login_password(
        request,
        payload.login,
        payload.password,
        action="admin_login_local",
    )
    token, _ = storage.create_admin_session(idle_timeout_seconds=admin_idle_timeout_seconds)
    _set_session_cookie(
        response=response,
        key=ADMIN_SESSION_COOKIE,
        value=token,
        max_age=admin_idle_timeout_seconds,
    )
    return None


@api.post("/admin/session", status_code=status.HTTP_204_NO_CONTENT)
async def create_admin_session(
    response: Response,
    _ip: str = Depends(verify_admin_key_header("admin_session_create_local")),
):
    token, _ = storage.create_admin_session(idle_timeout_seconds=admin_idle_timeout_seconds)
    _set_session_cookie(
        response=response,
        key=ADMIN_SESSION_COOKIE,
        value=token,
        max_age=admin_idle_timeout_seconds,
    )
    return None


@api.get("/admin/session", response_model=AdminSessionStateResponse)
async def get_admin_session_state(
    request: Request,
    _ip: str = Depends(get_admin_auth("admin_session_get_local")),
):
    token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error_payload(
                code="admin_session_missing",
                detail="Admin session is missing.",
                user_action="Login again to continue.",
            ),
        )
    active, reason, _ = storage.validate_admin_session(token, touch=False)
    if not active:
        code = "admin_session_expired" if reason == "expired" else "admin_session_invalid"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error_payload(
                code=code,
                detail="Admin session is invalid or expired.",
                user_action="Login again to continue.",
            ),
        )
    session_row = storage.get_admin_session(token)
    last_activity = None
    if session_row and session_row.get("last_activity_at"):
        try:
            last_activity = datetime.fromisoformat(session_row["last_activity_at"])
        except Exception:
            last_activity = None
    return AdminSessionStateResponse(
        active=True,
        idle_timeout_seconds=admin_idle_timeout_seconds,
        last_activity_at=last_activity,
    )


@api.delete("/admin/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_session(
    response: Response,
    request: Request,
    _ip: str = Depends(get_admin_auth("admin_session_delete_local")),
):
    token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
    if token:
        storage.revoke_admin_session(token)
    _delete_session_cookie(response, ADMIN_SESSION_COOKIE)
    return None


def _find_account_public(account_id: str) -> Optional[dict]:
    for row in acc_store.list_accounts():
        if row.get("id") == account_id:
            return row
    return None


def _warmup_window(ts_now: datetime, ttl_seconds: int, cooldown_seconds: int) -> tuple[str, str, str]:
    last_success_at = ts_now.isoformat()
    expires_at = (ts_now + timedelta(seconds=max(0, ttl_seconds))).isoformat()
    cooldown_until = (ts_now + timedelta(seconds=max(0, cooldown_seconds))).isoformat()
    return last_success_at, expires_at, cooldown_until


async def _execute_account_warmup(
    *,
    account: dict,
    run_id: str,
    models: list[str],
    mode: str,
    force: bool,
    ttl_seconds: int,
    cooldown_seconds: int,
) -> dict:
    account_id = str(account["id"])
    workspace = str(account.get("workspace") or "").strip()
    result_payload: dict[str, Any] = {
        "account_id": account_id,
        "workspace": workspace,
        "scheduled": [],
        "failed": [],
        "skipped": [],
        "mode": mode,
    }

    if account.get("status") != "ready":
        for model in models:
            acc_store.record_warmup_item(
                run_id=run_id,
                account_id=account_id,
                model=model,
                result="skipped",
                reason=f"status={account.get('status')}",
            )
            result_payload["skipped"].append({"model": model, "reason": f"status={account.get('status')}"})
        return result_payload

    warm_models: list[str] = []
    for model in models:
        if (not force) and acc_store.is_warmup_cooldown_active(account_id, model):
            acc_store.record_warmup_item(
                run_id=run_id,
                account_id=account_id,
                model=model,
                result="skipped",
                reason="cooldown_active",
            )
            result_payload["skipped"].append({"model": model, "reason": "cooldown_active"})
            continue
        warm_models.append(model)

    if not warm_models:
        return result_payload

    if not workspace:
        for model in warm_models:
            acc_store.record_warmup_item(
                run_id=run_id,
                account_id=account_id,
                model=model,
                result="failed",
                error="workspace_not_configured",
            )
            state = acc_store.get_warmup_state(account_id, model) or {}
            acc_store.upsert_warmup_state(
                account_id=account_id,
                model=model,
                last_success_at=state.get("last_success_at"),
                expires_at=state.get("expires_at"),
                cooldown_until=state.get("cooldown_until"),
                last_run_id=run_id,
                last_error="workspace_not_configured",
            )
            result_payload["failed"].append({"model": model, "error": "workspace_not_configured"})
        return result_payload

    details = trigger_workspace_warmup_detailed(
        workspace=workspace,
        account_id=account_id,
        models=warm_models,
        mode=mode,
    )
    scheduled_map = details.get("scheduled", {}) or {}
    error_rows = details.get("errors", []) or []
    error_by_model: dict[str, str] = {}
    for row in error_rows:
        model = str(row.get("model", "")).strip().lower()
        if model:
            error_by_model[model] = str(row.get("error", "warmup_failed"))

    ts_now = datetime.now(timezone.utc)
    last_success_at, expires_at, cooldown_until = _warmup_window(
        ts_now,
        ttl_seconds=ttl_seconds,
        cooldown_seconds=cooldown_seconds,
    )

    for model in warm_models:
        if model in scheduled_map:
            task_id = str(scheduled_map[model])
            acc_store.record_warmup_item(
                run_id=run_id,
                account_id=account_id,
                model=model,
                task_id=task_id,
                result="done",
            )
            acc_store.upsert_warmup_state(
                account_id=account_id,
                model=model,
                last_success_at=last_success_at,
                expires_at=expires_at,
                cooldown_until=cooldown_until,
                last_run_id=run_id,
                last_error=None,
            )
            result_payload["scheduled"].append({"model": model, "task_id": task_id})
        else:
            error_msg = error_by_model.get(model) or str(details.get("error") or "warmup_not_scheduled")
            acc_store.record_warmup_item(
                run_id=run_id,
                account_id=account_id,
                model=model,
                result="failed",
                error=error_msg,
            )
            state = acc_store.get_warmup_state(account_id, model) or {}
            acc_store.upsert_warmup_state(
                account_id=account_id,
                model=model,
                last_success_at=state.get("last_success_at"),
                expires_at=state.get("expires_at"),
                cooldown_until=state.get("cooldown_until"),
                last_run_id=run_id,
                last_error=error_msg,
            )
            result_payload["failed"].append({"model": model, "error": error_msg})

    return result_payload


@api.get("/admin/health")
async def admin_health(_ip: str = Depends(get_admin_auth("admin_health_local"))):
    ready = [a for a in acc_store.list_accounts() if a["status"] == "ready"]
    return {
        "ok": True,
        "storage_ok": storage.check_storage_health(),
        "ready_accounts": len(ready),
        "diagnostics": storage.get_operational_snapshot(),
    }


@api.get("/admin/setup/requirements")
async def admin_setup_requirements(_ip: str = Depends(get_admin_auth("admin_setup_requirements_local"))):
    return _shared_env_requirements_payload()


@api.post("/admin/setup/validate")
async def admin_setup_validate(_ip: str = Depends(get_admin_auth("admin_setup_validate_local"))):
    payload = _shared_env_requirements_payload()
    if payload["ready"]:
        return payload
    has_service_blocker = bool(payload.get("missing_env")) or any(
        c.get("code") == "modal_cli_unavailable" for c in payload.get("categories", [])
    )
    status_code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if has_service_blocker
        else status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    detail = _error_payload(
        code="admin_setup_not_ready",
        detail="Shared environment is not ready for account onboarding.",
        user_action="Resolve setup categories from metadata and retry.",
    )
    detail["metadata"] = {
        "checks": payload.get("checks", {}),
        "categories": payload.get("categories", []),
        "missing_env": payload.get("missing_env", []),
        "validation_errors": payload.get("validation_errors", []),
    }
    raise HTTPException(
        status_code=status_code,
        detail=detail,
    )


@api.get("/admin/accounts")
async def admin_list_accounts(_ip: str = Depends(get_admin_auth("list_accounts_local"))):
    return {
        "accounts": acc_store.list_accounts(),
        "diagnostics": storage.get_operational_snapshot(),
        "events": storage.list_operational_events(limit=30),
    }


@api.post("/admin/accounts", status_code=201)
async def admin_add_account(
    label: str = Body(...),
    token_id: str = Body(...),
    token_secret: str = Body(...),
    _ip: str = Depends(get_admin_auth("add_account_local")),
):
    setup_payload = _shared_env_requirements_payload()
    if setup_payload["missing_env"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_payload(
                code="missing_shared_env",
                detail="Missing required shared env: " + ", ".join(setup_payload["missing_env"]),
                user_action=(
                    "Set required env vars (API_KEY, ADMIN_LOGIN, ADMIN_PASSWORD_HASH, "
                    "ACCOUNTS_ENCRYPT_KEY, HF_TOKEN) in VM runtime and restart container."
                ),
            ),
        )
    modal_cli_check = (setup_payload.get("checks") or {}).get("modal_cli") or {}
    if modal_cli_check.get("status") != "ok":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_payload(
                code="modal_cli_unavailable",
                detail=str(modal_cli_check.get("message") or "Modal CLI check failed."),
                user_action="Install Modal CLI so `python -m modal --version` works, then retry.",
            ),
        )
    if setup_payload["validation_errors"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                code="invalid_shared_env",
                detail="Invalid shared env values: " + "; ".join(setup_payload["validation_errors"]),
                user_action="Fix invalid env values and retry.",
            ),
        )
    try:
        account_id = acc_store.add_account(
            label=label,
            token_id=token_id,
            token_secret=token_secret,
        )
    except acc_store.DuplicateAccountError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_error_payload(
                code="account_already_exists",
                detail=str(exc),
                user_action="Use a different Modal account or delete the existing duplicate first.",
            ),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_payload(
                code="admin_storage_misconfigured",
                detail=str(exc),
                user_action="Set ACCOUNTS_ENCRYPT_KEY in VM env and restart container.",
            ),
        ) from exc
    deploy_account_async(account_id)
    return {"id": account_id, "status": "pending", "message": "Deploying..."}


@api.delete("/admin/accounts/{account_id}")
async def admin_delete_account(
    account_id: str,
    _ip: str = Depends(get_admin_auth("delete_account_local")),
):
    deleted = acc_store.delete_account(account_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(
                code="not_found",
                detail="Account not found.",
                user_action="Verify account id and retry.",
            ),
        )
    return {"deleted": True, "id": account_id}


@api.post("/admin/accounts/{account_id}/disable")
async def admin_disable_account(
    account_id: str,
    _ip: str = Depends(get_admin_auth("disable_account_local")),
):
    acc_store.disable_account(account_id)
    return {"id": account_id, "status": "disabled"}


@api.post("/admin/accounts/{account_id}/enable")
async def admin_enable_account(
    account_id: str,
    _ip: str = Depends(get_admin_auth("enable_account_local")),
):
    if acc_store.get_account(account_id) is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(
                code="not_found",
                detail="Account not found.",
                user_action="Verify account id and retry.",
            ),
        )
    acc_store.enable_account(account_id)
    return {"id": account_id, "status": "ready", "message": "Account enabled and returned to rotation."}


@api.post("/admin/accounts/{account_id}/reset-usage")
async def admin_reset_usage(
    account_id: str,
    _ip: str = Depends(get_admin_auth("reset_usage_local")),
):
    acc_store.reset_monthly_usage(account_id)
    return {"ok": True}


@api.post("/admin/reset-all-usage")
async def admin_reset_all_usage(_ip: str = Depends(get_admin_auth("reset_all_usage_local"))):
    acc_store.reset_monthly_usage()
    return {"ok": True}


@api.post("/admin/accounts/{account_id}/deploy")
async def admin_deploy_account(
    account_id: str,
    _ip: str = Depends(get_admin_auth("deploy_account_local")),
):
    if acc_store.get_account(account_id) is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(
                code="not_found",
                detail="Account not found.",
                user_action="Verify account id and retry.",
            ),
        )
    deploy_account_async(account_id)
    return {"id": account_id, "status": "checking", "message": "Deploy started, health-check in progress."}


@api.post("/admin/deploy-all")
async def admin_deploy_all(_ip: str = Depends(get_admin_auth("deploy_all_local"))):
    threads = deploy_all_accounts()
    return {"deploying": len(threads), "message": f"Deploying {len(threads)} account(s)..."}


@api.post("/admin/accounts/{account_id}/warmup")
async def admin_warmup_account(
    account_id: str,
    payload: dict[str, Any] = Body(default={}),
    _ip: str = Depends(get_admin_auth("warmup_account_local")),
):
    account = _find_account_public(account_id)
    if account is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(
                code="not_found",
                detail="Account not found.",
                user_action="Verify account id and retry.",
            ),
        )
    models = _parse_warmup_models(payload.get("models"))
    mode = _parse_warmup_mode(payload.get("mode", "best_effort"))
    force = bool(payload.get("force", False))
    ttl_seconds = _parse_positive_int(payload.get("ttl_seconds"), WARMUP_TTL_SECONDS, "ttl_seconds")
    cooldown_seconds = _parse_positive_int(payload.get("cooldown_seconds"), WARMUP_COOLDOWN_SECONDS, "cooldown_seconds")

    run_id = acc_store.create_warmup_run(
        triggered_by="admin_local",
        mode=mode,
        account_ids=[account_id],
        models=models,
    )
    account_result = await _execute_account_warmup(
        account=account,
        run_id=run_id,
        models=models,
        mode=mode,
        force=force,
        ttl_seconds=ttl_seconds,
        cooldown_seconds=cooldown_seconds,
    )
    failed_items = len(account_result["failed"])
    status_value = "failed" if (mode == "required" and failed_items > 0) else "completed"
    summary = {
        "mode": mode,
        "models": models,
        "accounts_total": 1,
        "accounts_completed": 1,
        "failed_items": failed_items,
        "force": force,
        "ttl_seconds": ttl_seconds,
        "cooldown_seconds": cooldown_seconds,
        "results": [account_result],
    }
    acc_store.finalize_warmup_run(run_id, status=status_value, summary=summary)
    return {"run_id": run_id, "status": status_value, **summary}


@api.post("/admin/warmup")
async def admin_warmup_batch(
    payload: dict[str, Any] = Body(default={}),
    _ip: str = Depends(get_admin_auth("warmup_batch_local")),
):
    all_accounts = acc_store.list_accounts()
    filter_ids = payload.get("account_ids")
    if filter_ids is not None and not isinstance(filter_ids, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                code="validation_error",
                detail="account_ids must be an array.",
                user_action="Provide a valid account_ids array.",
            ),
        )
    filter_set = {str(v) for v in (filter_ids or [])}
    target_accounts = [
        row for row in all_accounts
        if (not filter_set or row.get("id") in filter_set)
    ]
    models = _parse_warmup_models(payload.get("models"))
    mode = _parse_warmup_mode(payload.get("mode", "best_effort"))
    force = bool(payload.get("force", False))
    ttl_seconds = _parse_positive_int(payload.get("ttl_seconds"), WARMUP_TTL_SECONDS, "ttl_seconds")
    cooldown_seconds = _parse_positive_int(payload.get("cooldown_seconds"), WARMUP_COOLDOWN_SECONDS, "cooldown_seconds")

    run_id = acc_store.create_warmup_run(
        triggered_by="admin_local",
        mode=mode,
        account_ids=[str(a.get("id")) for a in target_accounts],
        models=models,
    )

    results: list[dict[str, Any]] = []
    failed_items = 0
    for account in target_accounts:
        account_result = await _execute_account_warmup(
            account=account,
            run_id=run_id,
            models=models,
            mode=mode,
            force=force,
            ttl_seconds=ttl_seconds,
            cooldown_seconds=cooldown_seconds,
        )
        failed_items += len(account_result["failed"])
        results.append(account_result)

    status_value = "failed" if (mode == "required" and failed_items > 0) else "completed"
    summary = {
        "mode": mode,
        "models": models,
        "accounts_total": len(target_accounts),
        "accounts_completed": len(results),
        "failed_items": failed_items,
        "force": force,
        "ttl_seconds": ttl_seconds,
        "cooldown_seconds": cooldown_seconds,
        "results": results,
    }
    acc_store.finalize_warmup_run(run_id, status=status_value, summary=summary)
    return {"run_id": run_id, "status": status_value, **summary}


@api.get("/admin/warmup-runs/{run_id}")
async def admin_warmup_run_status(
    run_id: str,
    _ip: str = Depends(get_admin_auth("warmup_run_status_local")),
):
    run = acc_store.get_warmup_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(
                code="not_found",
                detail="Warmup run not found.",
                user_action="Verify run id and retry.",
            ),
        )
    items = acc_store.list_warmup_items(run_id)
    return {"run": run, "items": items}


@api.get("/admin/logs")
async def admin_get_logs(
    limit: int = 100,
    _ip: str = Depends(get_admin_auth("read_logs_local")),
):
    return {"logs": storage.get_audit_logs(limit=limit)}

