"""
Local VM API for admin + generation proxy.

This service runs behind nginx at same-origin `/api/*` and is used by the
frontend to avoid browser CORS/cookie issues with direct cross-origin Modal
calls. It only routes generation through explicitly configured ready accounts.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

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
from deployer import deploy_account_async, deploy_all_accounts, get_missing_shared_env_keys
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


def _error_payload(*, code: str, detail: str, user_action: str) -> dict:
    return {"code": code, "detail": detail, "user_action": user_action}


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


def _build_remote_base(workspace: str) -> str:
    ws = workspace.strip()
    if not ws:
        raise ValueError("workspace is empty")
    return f"https://{ws}--gooni-api.modal.run"


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
    base = _build_remote_base(workspace)
    try:
        timeout = httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=5.0)
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
            raise RuntimeError(f"remote_{resp.status_code}:{resp.text[:200]}")
        payload = resp.json()
        if isinstance(payload, dict):
            payload["task_id"] = f"{workspace}::{remote_task_id}"
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=_error_payload(
                code="remote_status_unavailable",
                detail=f"Remote status fetch failed: {exc}",
                user_action="Retry shortly.",
            ),
        ) from exc


async def _proxy_binary(workspace: str, remote_task_id: str, path: str, api_key: str, *, read_timeout: float) -> Response:
    base = _build_remote_base(workspace)
    try:
        timeout = httpx.Timeout(connect=5.0, read=read_timeout, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{base}/{path}/{remote_task_id}",
                headers={"X-API-Key": api_key},
            )
        if resp.status_code == 404:
            code = "result_not_found" if path == "results" else "preview_not_found"
            raise HTTPException(
                status_code=404,
                detail=_error_payload(
                    code=code,
                    detail=f"Remote {path[:-1]} not found.",
                    user_action="Verify task id or regenerate.",
                ),
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"remote_{resp.status_code}:{resp.text[:200]}")
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "application/octet-stream"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        code = "remote_result_unavailable" if path == "results" else "remote_preview_unavailable"
        raise HTTPException(
            status_code=502,
            detail=_error_payload(
                code=code,
                detail=f"Remote {path} fetch failed: {exc}",
                user_action="Retry shortly.",
            ),
        ) from exc


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


@api.on_event("startup")
def _startup() -> None:
    os.makedirs("/results", exist_ok=True)
    storage.init_db()
    acc_store.init_accounts_table()
    _ensure_audit_table()


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

    for attempt in range(MAX_FALLBACKS + 1):
        try:
            account = account_router.pick() if attempt == 0 else account_router.pick_with_fallback(tried=tried_accounts)
            account_id = str(account["id"])
            tried_accounts.append(account_id)

            workspace = (account.get("workspace") or "").strip()
            if not workspace:
                raise RuntimeError("workspace_not_configured")

            base = _build_remote_base(workspace)
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
            return GenerateResponse(task_id=f"{workspace}::{remote_task_id}", status=TaskStatus.pending)

        except HTTPException:
            raise
        except NoReadyAccountError as exc:
            last_error = str(exc)
            break
        except Exception as exc:
            last_error = str(exc)
            if tried_accounts:
                account_router.mark_failed(tried_accounts[-1], last_error)
            if not _is_retryable_remote_error(exc):
                break

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


@api.get("/admin/health")
async def admin_health(_ip: str = Depends(get_admin_auth("admin_health_local"))):
    ready = [a for a in acc_store.list_accounts() if a["status"] == "ready"]
    return {
        "ok": True,
        "storage_ok": storage.check_storage_health(),
        "ready_accounts": len(ready),
        "diagnostics": storage.get_operational_snapshot(),
    }


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
    missing_env = get_missing_shared_env_keys()
    if missing_env:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_payload(
                code="admin_env_missing",
                detail="Missing required shared env: " + ", ".join(missing_env),
                user_action=(
                    "Set required env vars (API_KEY, ADMIN_LOGIN, ADMIN_PASSWORD_HASH, "
                    "ACCOUNTS_ENCRYPT_KEY, HF_TOKEN) in VM runtime and restart container."
                ),
            ),
        )
    try:
        account_id = acc_store.add_account(
            label=label,
            token_id=token_id,
            token_secret=token_secret,
        )
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


@api.get("/admin/logs")
async def admin_get_logs(
    limit: int = 100,
    _ip: str = Depends(get_admin_auth("read_logs_local")),
):
    return {"logs": storage.get_audit_logs(limit=limit)}
