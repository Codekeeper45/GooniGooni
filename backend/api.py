"""
api.py
──────
FastAPI application factory.

Previously this code lived inside the fastapi_app() function in app.py.
Extracting it here makes app.py purely about Modal setup (functions, volumes,
Docker images, schedules) while api.py owns the HTTP layer.

Usage inside app.py:
    @modal.asgi_app(label="gooni-api")
    def fastapi_app():
        from api import create_app
        return create_app()
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status, Body
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

import storage
import accounts as acc_store
from auth import verify_api_key, verify_generation_session, GENERATION_SESSION_COOKIE
from admin_security import (
    _ensure_audit_table,
    get_admin_auth,
    verify_admin_login_password,
    verify_admin_key_header,
    ADMIN_SESSION_COOKIE,
)
from config import (
    MODELS_SCHEMA,
    DEFAULT_PAGE_SIZE,
    DEGRADED_QUEUE_MAX_DEPTH,
    DEGRADED_QUEUE_MAX_WAIT_SECONDS,
    DEGRADED_QUEUE_OVERLOAD_CODE,
    GEN_SESSION_MAX_ACTIVE_TASKS,
    NO_READY_ACCOUNT_WAIT_SECONDS,
    ARTIFACT_TTL_DAYS,
)
from router import router as account_router, NoReadyAccountError, MAX_FALLBACKS
from deployer import (
    deploy_account_async,
    deploy_all_accounts,
    get_missing_shared_env_keys,
    trigger_workspace_warmup_detailed,
)
from schemas import (
    AdminLoginRequest,
    AdminSessionStateResponse,
    DeleteResponse,
    GalleryResponse,
    GenerateRequest,
    GenerateResponse,
    GenerationSessionStateResponse,
    HealthResponse,
    ModelsResponse,
    StatusResponse,
    TaskStatus,
    ErrorResponse,
)


# ─── These are set by create_app() from Modal volume ref ──────────────────────
_results_vol = None  # injected at startup
_VALID_WARMUP_MODELS = ("anisora", "phr00t", "pony", "flux")
_DEFAULT_ADMIN_WARMUP_MODELS = tuple(
    m.strip().lower()
    for m in os.environ.get("WARMUP_DEFAULT_MODELS", "pony,flux").split(",")
    if m.strip().lower() in _VALID_WARMUP_MODELS
) or ("pony", "flux")
WARMUP_TTL_SECONDS = max(300, int(os.environ.get("WARMUP_TTL_SECONDS", "21600")))
WARMUP_COOLDOWN_SECONDS = max(0, int(os.environ.get("WARMUP_COOLDOWN_SECONDS", "3600")))


def _set_results_vol(vol):
    global _results_vol
    _results_vol = vol


def _vol_reload():
    if _results_vol is not None:
        _results_vol.reload()


def _vol_commit():
    if _results_vol is not None:
        _results_vol.commit()


# ─── Error helpers ────────────────────────────────────────────────────────────

_ERROR_CODE_BY_STATUS = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden",
    404: "not_found", 409: "conflict", 410: "resource_gone",
    422: "validation_error", 429: "rate_limited",
    500: "internal_error", 502: "upstream_error", 503: "service_unavailable",
}
_USER_ACTION_BY_STATUS = {
    400: "Check request parameters and retry.",
    401: "Re-authenticate and retry.",
    403: "Check credentials and retry.",
    404: "Verify the identifier and retry.",
    409: "Retry the operation.",
    410: "Regenerate the asset and retry.",
    422: "Fix request fields and retry.",
    429: "Retry after a short delay.",
    500: "Retry later.", 502: "Retry shortly.", 503: "Retry later.",
}


def _error_payload(code: str, detail: str, user_action: str) -> dict:
    return ErrorResponse(code=code, detail=detail, user_action=user_action).model_dump()


def _as_api_error(status_code: int, detail: object) -> dict:
    if isinstance(detail, dict):
        code = str(detail.get("code") or _ERROR_CODE_BY_STATUS.get(status_code, "request_failed"))
        message = str(detail.get("detail") or "Request failed.")
        action = str(detail.get("user_action") or _USER_ACTION_BY_STATUS.get(status_code, "Retry later."))
        payload = _error_payload(code=code, detail=message, user_action=action)
        if isinstance(detail.get("metadata"), dict):
            payload["metadata"] = detail["metadata"]
        return payload
    if isinstance(detail, str):
        return _error_payload(
            code=_ERROR_CODE_BY_STATUS.get(status_code, "request_failed"),
            detail=detail,
            user_action=_USER_ACTION_BY_STATUS.get(status_code, "Retry later."),
        )
    return _error_payload(
        code=_ERROR_CODE_BY_STATUS.get(status_code, "request_failed"),
        detail="Request failed.",
        user_action=_USER_ACTION_BY_STATUS.get(status_code, "Retry later."),
    )


def _parse_warmup_mode(raw_mode: Any) -> str:
    mode = str(raw_mode or "best_effort").strip().lower()
    if mode not in {"required", "best_effort"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                "validation_error",
                "Warmup mode must be 'required' or 'best_effort'.",
                "Fix warmup mode and retry.",
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
                "validation_error",
                "Warmup models must be an array of model ids.",
                "Provide at least one valid model id.",
            ),
        )
    parsed = []
    for item in raw_models:
        model = str(item).strip().lower()
        if model not in _VALID_WARMUP_MODELS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_error_payload(
                    "validation_error",
                    f"Unsupported warmup model: {item}",
                    "Use one of: anisora, phr00t, pony, flux.",
                ),
            )
        if model not in parsed:
            parsed.append(model)
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                "validation_error",
                "Warmup models list cannot be empty.",
                "Provide at least one valid model id.",
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
                "validation_error",
                f"{field_name} must be an integer.",
                "Provide a valid integer and retry.",
            ),
        )
    if value < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                "validation_error",
                f"{field_name} cannot be negative.",
                "Provide a value >= 0 and retry.",
            ),
        )
    return value


# ─── Request helpers ──────────────────────────────────────────────────────────

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


def _fallback_reason_from_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "quota" in text:
        return "quota"
    if "manual" in text:
        return "manual"
    return "capacity"


def _is_remote_public_task_id(task_id: str) -> bool:
    return "::" in task_id


def _split_remote_public_task_id(task_id: str) -> tuple[str, str]:
    workspace, remote_task_id = task_id.split("::", 1)
    return workspace.strip(), remote_task_id.strip()


def _compose_remote_public_task_id(workspace: str, remote_task_id: str) -> str:
    return f"{workspace}::{remote_task_id}"


def _remote_workspace_base_url(workspace: str) -> str:
    return f"https://{workspace}--gooni-api.modal.run"


def _extract_generation_session_token(session_or_api_key: str) -> Optional[str]:
    """
    verify_generation_session returns either:
      - generation session token
      - API key (header/query fallback path)
    Here we only need the actual generation session token.
    """
    active, _, _ = storage.validate_generation_session(session_or_api_key)
    return session_or_api_key if active else None


def _gateway_media_urls(request: Request, task_id: str) -> tuple[str, str]:
    base_url = str(request.base_url).rstrip("/")
    return (f"{base_url}/results/{task_id}", f"{base_url}/preview/{task_id}")


def _no_ready_wait_remaining(deadline: float, now: Optional[float] = None) -> float:
    current = time.monotonic() if now is None else now
    return max(0.0, deadline - current)


def _no_ready_wait_expired(deadline: float, now: Optional[float] = None) -> bool:
    return _no_ready_wait_remaining(deadline, now=now) <= 0.0


# ─── Cookie helpers ───────────────────────────────────────────────────────────

_COOKIE_SECURE = True
_COOKIE_SAMESITE = "none"


def _set_session_cookie(response: Response, key: str, value: str, max_age: int) -> None:
    response.set_cookie(
        key=key, value=value, max_age=max_age,
        httponly=True, secure=_COOKIE_SECURE, samesite=_COOKIE_SAMESITE, path="/",
    )


def _delete_session_cookie(response: Response, key: str) -> None:
    response.delete_cookie(
        key=key, httponly=True, secure=_COOKIE_SECURE, samesite=_COOKIE_SAMESITE, path="/",
    )


# ─── Application factory ──────────────────────────────────────────────────────

def create_app(results_vol=None) -> FastAPI:
    """
    Build and return the configured FastAPI application.
    Pass `results_vol` to enable volume reload/commit inside routes.
    """
    if results_vol is not None:
        _set_results_vol(results_vol)

    # Init DB
    storage.init_db()
    acc_store.init_accounts_table()
    _ensure_audit_table()

    enable_docs = (os.environ.get("ENABLE_DOCS", "0").strip().lower() in {"1", "true", "yes", "on"})
    if not os.environ.get("PUBLIC_BASE_URL", "").strip():
        print("[CONFIG] PUBLIC_BASE_URL is not set; /status links may be null.")

    api = FastAPI(
        title="Gooni Gooni Backend",
        description="AI content generation API (images & videos)",
        version="1.0.0",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
    )

    # CORS
    env_origins = [o.strip() for o in os.environ.get("FRONTEND_ORIGINS", "").split(",") if o.strip()]
    default_origins = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://34.73.173.191", "https://34.73.173.191",
    ]
    api.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(set(default_origins + env_origins)),
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|34\.73\.173\.191)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global config
    generation_ttl = int(os.environ.get("GENERATION_SESSION_TTL_SECONDS", str(24 * 3600)))
    admin_idle_timeout = int(os.environ.get("ADMIN_SESSION_IDLE_TIMEOUT_SECONDS", str(12 * 3600)))

    # ── Exception handlers ────────────────────────────────────────────────────

    @api.exception_handler(HTTPException)
    async def _http_exception_handler(_: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_as_api_error(exc.status_code, exc.detail),
            headers=exc.headers,
        )

    @api.exception_handler(RequestValidationError)
    async def _validation_exception_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                **_error_payload("validation_error", "Request validation failed.", "Fix request fields and retry."),
                "metadata": {"errors": exc.errors()},
            },
        )

    # ── Degraded queue helpers ────────────────────────────────────────────────

    import asyncio
    import time

    async def _admit_degraded_queue(task_id: str, model_key: str) -> tuple[bool, float, int]:
        started = time.monotonic()
        while True:
            admitted, depth = storage.try_admit_degraded_task(task_id, max_depth=DEGRADED_QUEUE_MAX_DEPTH)
            waited = time.monotonic() - started
            if admitted:
                storage.record_operational_event("queue_admitted", task_id=task_id, model=model_key, lane_mode="degraded_shared", value=depth)
                return True, waited, depth
            if waited >= DEGRADED_QUEUE_MAX_WAIT_SECONDS:
                storage.record_operational_event("queue_timeout", task_id=task_id, model=model_key, lane_mode="degraded_shared", value=round(waited, 3))
                return False, waited, depth
            await asyncio.sleep(0.5)

    # ── Generation orchestration (imported functions from app.py at runtime) ──

    async def _spawn_local_generation(
        req: GenerateRequest,
        *,
        force_degraded_reason: Optional[str] = None,
        warmup_only: bool = False,
        generation_session_token: Optional[str] = None,
    ) -> GenerateResponse:
        import random
        # Late import to access Modal spawnable functions
        from app import (
            run_anisora_generation,
            run_flux_generation,
            run_image_generation,
            run_phr00t_generation,
            run_pony_generation,
            run_video_generation,
            results_vol as _rvol,
        )

        params = req.model_dump(exclude={"prompt", "negative_prompt", "model", "type", "mode", "width", "height", "seed", "reference_image", "first_frame_image", "last_frame_image", "arbitrary_frames"})
        model_key = req.model.value
        lane_mode: Optional[str] = "dedicated"
        resolved_seed = req.seed if req.seed != -1 else random.randint(0, 2_147_483_647)

        task_id = storage.create_task(
            model=model_key, gen_type=req.type.value, mode=req.mode,
            prompt=req.prompt, negative_prompt=req.negative_prompt,
            parameters=params, width=req.width, height=req.height,
            seed=resolved_seed, lane_mode=lane_mode, fallback_reason=force_degraded_reason,
            generation_session_token=generation_session_token,
            artifact_ttl_days=ARTIFACT_TTL_DAYS,
        )
        req_dict = _normalize_request_dict(req)
        req_dict["seed"] = resolved_seed
        if warmup_only:
            req_dict["_warmup_only"] = True

        # Image lane — dedicated first, degraded fallback
        if req.type.value != "video":
            fallback_reason = force_degraded_reason
            if fallback_reason is None:
                try:
                    storage.update_task_status(task_id, "pending", progress=0, stage="queued", stage_detail="dedicated_lane", lane_mode="dedicated")
                    _rvol.commit()
                    if model_key == "pony":
                        run_pony_generation.spawn(req_dict, task_id)
                    elif model_key == "flux":
                        run_flux_generation.spawn(req_dict, task_id)
                    else:
                        raise ValueError(f"Unsupported image model: {model_key}")
                    storage.record_operational_event("warm_lane_ready", task_id=task_id, model=model_key, lane_mode="dedicated")
                    _rvol.commit()
                    return GenerateResponse(task_id=task_id, status=TaskStatus.pending)
                except Exception as exc:
                    fallback_reason = _fallback_reason_from_error(exc)
                    storage.record_operational_event("fallback_activated", task_id=task_id, model=model_key, lane_mode="degraded_shared", reason=fallback_reason)

            req_dict["_fallback_reason"] = fallback_reason or "capacity"
            storage.update_task_status(task_id, "pending", progress=0, stage="queued", stage_detail="degraded_image_lane", lane_mode="degraded_shared", fallback_reason=fallback_reason)
            _rvol.commit()
            try:
                run_image_generation.spawn(req_dict, task_id)
            except Exception as exc:
                storage.update_task_status(task_id, "failed", error_msg=f"Spawn failed: {exc}", stage="failed", stage_detail="degraded_spawn_failed", lane_mode="degraded_shared", fallback_reason=fallback_reason)
                _rvol.commit()
                raise HTTPException(status_code=503, detail=_error_payload("enqueue_failed", "Failed to enqueue image generation task.", "Retry later."))
            storage.record_operational_event("queue_depth", task_id=task_id, model=model_key, lane_mode="degraded_shared", reason=fallback_reason)
            _rvol.commit()
            return GenerateResponse(task_id=task_id, status=TaskStatus.pending)

        # Video lane — dedicated first, degraded fallback
        fallback_reason = force_degraded_reason
        if fallback_reason is None:
            try:
                storage.update_task_status(task_id, "pending", progress=0, stage="queued", stage_detail="dedicated_lane", lane_mode="dedicated")
                _rvol.commit()
                if model_key == "anisora":
                    run_anisora_generation.spawn(req_dict, task_id)
                elif model_key == "phr00t":
                    run_phr00t_generation.spawn(req_dict, task_id)
                else:
                    raise ValueError(f"Unsupported video model: {model_key}")
                storage.record_operational_event("warm_lane_ready", task_id=task_id, model=model_key, lane_mode="dedicated")
                return GenerateResponse(task_id=task_id, status=TaskStatus.pending)
            except Exception as exc:
                fallback_reason = _fallback_reason_from_error(exc)
                storage.record_operational_event("fallback_activated", task_id=task_id, model=model_key, lane_mode="degraded_shared", reason=fallback_reason)

        # Degraded shared video lane
        admitted, waited, depth = await _admit_degraded_queue(task_id, model_key)
        if not admitted:
            storage.update_task_status(task_id, "failed", error_msg=DEGRADED_QUEUE_OVERLOAD_CODE, stage="rejected", stage_detail=DEGRADED_QUEUE_OVERLOAD_CODE, lane_mode="degraded_shared", fallback_reason=fallback_reason)
            storage.record_operational_event("queue_overloaded", task_id=task_id, model=model_key, lane_mode="degraded_shared", value=depth, reason=fallback_reason)
            _rvol.commit()
            raise HTTPException(status_code=503, detail={**_error_payload(DEGRADED_QUEUE_OVERLOAD_CODE, f"Generation queue is overloaded (depth={depth}).", "Retry later."), "metadata": {"depth": depth, "max_depth": DEGRADED_QUEUE_MAX_DEPTH, "max_wait_seconds": DEGRADED_QUEUE_MAX_WAIT_SECONDS}})

        req_dict["_fallback_reason"] = fallback_reason or "capacity"
        req_dict["_degraded_wait_seconds"] = round(waited, 3)
        req_dict["_degraded_queue_depth"] = depth
        storage.update_task_status(task_id, "pending", progress=0, stage="queued", stage_detail=f"degraded_wait={round(waited,3)}s", lane_mode="degraded_shared", fallback_reason=fallback_reason)
        _rvol.commit()

        try:
            run_video_generation.spawn(req_dict, task_id)
        except Exception as exc:
            storage.release_degraded_task(task_id)
            storage.update_task_status(task_id, "failed", error_msg=f"Spawn failed: {exc}", stage="failed", stage_detail="degraded_spawn_failed", lane_mode="degraded_shared", fallback_reason=fallback_reason)
            _rvol.commit()
            raise HTTPException(status_code=503, detail=_error_payload("enqueue_failed", "Failed to enqueue degraded video generation task.", "Retry later."))

        storage.record_operational_event("queue_depth", task_id=task_id, model=model_key, lane_mode="degraded_shared", value=depth, reason=fallback_reason)
        _rvol.commit()
        return GenerateResponse(task_id=task_id, status=TaskStatus.pending)

    # ─────────────────────────────────────────────────────────────────────────
    # ROUTES
    # ─────────────────────────────────────────────────────────────────────────

    # ── Health ────────────────────────────────────────────────────────────────
    @api.get("/health", response_model=HealthResponse, tags=["Info"])
    async def health_check():
        return HealthResponse()

    @api.get("/models", response_model=ModelsResponse, tags=["Info"])
    async def list_models(_: str = Depends(verify_api_key)):
        return ModelsResponse(models=MODELS_SCHEMA)

    # ── Auth / Session ────────────────────────────────────────────────────────
    @api.post("/auth/session", status_code=status.HTTP_204_NO_CONTENT, tags=["Auth"])
    async def create_generation_session(response: Response, request: Request):
        _vol_reload()
        client_ip = request.client.host if request.client else "unknown"
        token, _ = storage.create_generation_session(ttl_seconds=generation_ttl, client_context=client_ip)
        _vol_commit()
        _set_session_cookie(response, GENERATION_SESSION_COOKIE, token, generation_ttl)
        return None

    @api.get("/auth/session", response_model=GenerationSessionStateResponse, tags=["Auth"])
    async def get_generation_session_state(request: Request):
        token = request.cookies.get(GENERATION_SESSION_COOKIE, "")
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "generation_session_missing", "detail": "Generation session is missing.", "user_action": "Create a new session and retry."})
        _vol_reload()
        active, reason, expires_at = storage.validate_generation_session(token)
        if not active:
            code = "generation_session_expired" if reason == "expired" else "generation_session_invalid"
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": code, "detail": "Generation session is invalid or expired.", "user_action": "Create a new session and retry."})
        return GenerationSessionStateResponse(valid=True, active=True, expires_at=expires_at)

    @api.delete("/auth/session", status_code=status.HTTP_204_NO_CONTENT, tags=["Auth"])
    async def delete_generation_session(response: Response, request: Request):
        token = request.cookies.get(GENERATION_SESSION_COOKIE, "")
        if token:
            _vol_reload()
            storage.revoke_generation_session(token)
            _vol_commit()
        _delete_session_cookie(response, GENERATION_SESSION_COOKIE)
        return None

    # ── Generation ────────────────────────────────────────────────────────────
    @api.post("/generate_direct", response_model=GenerateResponse, tags=["Generation"])
    async def generate_direct(req: GenerateRequest, _: str = Depends(verify_api_key)):
        """Internal endpoint for isolated Modal account execution."""
        _vol_reload()
        return await _spawn_local_generation(req)

    @api.post("/warmup", tags=["Generation"])
    async def warmup_lanes(
        payload: dict[str, Any] = Body(default={}),
        _: str = Depends(verify_api_key),
    ):
        _vol_reload()
        enabled = (os.environ.get("ENABLE_LANE_WARMUP", "1").strip().lower() in {"1", "true", "yes", "on"})
        if not enabled:
            return {"ok": True, "enabled": False, "scheduled": []}

        mode = _parse_warmup_mode(payload.get("mode", "best_effort"))
        requested_models = _parse_warmup_models(payload.get("models"))
        wanted = set(requested_models)
        specs = [
            {
                "model": "anisora",
                "type": "video",
                "mode": "t2v",
                "prompt": "lane warmup",
                "width": 720,
                "height": 1280,
                "steps": 8,
            },
            {
                "model": "phr00t",
                "type": "video",
                "mode": "t2v",
                "prompt": "lane warmup",
                "width": 720,
                "height": 1280,
                "steps": 4,
                "cfg_scale": 1.0,
            },
            {
                "model": "pony",
                "type": "image",
                "mode": "txt2img",
                "prompt": "lane warmup",
                "width": 1024,
                "height": 1024,
                "steps": 30,
            },
            {
                "model": "flux",
                "type": "image",
                "mode": "txt2img",
                "prompt": "lane warmup",
                "width": 1024,
                "height": 1024,
                "steps": 25,
            },
        ]

        scheduled: list[dict] = []
        errors: list[dict] = []
        for spec in specs:
            if spec["model"] not in wanted:
                continue
            try:
                req = GenerateRequest(**spec)
                spawned = await _spawn_local_generation(
                    req,
                    warmup_only=True,
                )
                scheduled.append({"model": spec["model"], "task_id": spawned.task_id})
            except Exception as exc:
                errors.append({"model": spec["model"], "error": str(exc)})

        if mode == "required" and errors:
            raise HTTPException(
                status_code=503,
                detail=_error_payload(
                    "warmup_failed",
                    "Required warmup failed for one or more models.",
                    "Check worker availability and retry warmup.",
                ),
            )
        if errors and not scheduled:
            raise HTTPException(
                status_code=503,
                detail=_error_payload(
                    "warmup_failed",
                    "Failed to schedule lane warmup tasks.",
                    "Check worker availability and retry warmup.",
                ),
            )
        return {
            "ok": True,
            "enabled": True,
            "mode": mode,
            "requested_models": requested_models,
            "scheduled": scheduled,
            "errors": errors,
        }

    @api.post("/generate", response_model=GenerateResponse, tags=["Generation"])
    async def generate(req: GenerateRequest, session_or_api_key: str = Depends(verify_generation_session)):
        import httpx

        request_started_at = time.monotonic()
        _vol_reload()
        session_token = _extract_generation_session_token(session_or_api_key)
        if session_token:
            active_tasks = storage.count_active_tasks_for_session(session_token)
            if active_tasks >= GEN_SESSION_MAX_ACTIVE_TASKS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        **_error_payload(
                            "active_task_limit_exceeded",
                            "Too many active generation tasks for this session.",
                            "Wait for current tasks to finish, then retry.",
                        ),
                        "metadata": {
                            "active_tasks": active_tasks,
                            "limit": GEN_SESSION_MAX_ACTIVE_TASKS,
                        },
                    },
                )

        tried_accounts: list[str] = []
        last_error = ""
        api_key_env = os.environ.get("API_KEY", "")
        headers = {"X-API-Key": api_key_env} if api_key_env else {}
        req_payload = _normalize_request_dict(req)
        deadline = time.monotonic() + max(NO_READY_ACCOUNT_WAIT_SECONDS, 0)

        for attempt in range(MAX_FALLBACKS + 1):
            try:
                account = account_router.pick() if attempt == 0 else account_router.pick_with_fallback(tried=tried_accounts)
                tried_accounts.append(account["id"])
                workspace = account.get("workspace")
                if not workspace:
                    raise Exception("Account has no workspace configured.")
                remote_url = f"{_remote_workspace_base_url(workspace)}/generate_direct"
                async with httpx.AsyncClient(timeout=httpx.Timeout(connect=4.0, read=60.0, write=60.0, pool=5.0)) as client:
                    resp = await client.post(remote_url, json=req_payload, headers=headers)
                    if resp.status_code == 422:
                        payload = {}
                        try:
                            payload = resp.json()
                        except Exception:
                            pass
                        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
                        if isinstance(detail, dict) and {"code", "detail", "user_action"}.issubset(detail):
                            raise HTTPException(status_code=422, detail=detail)
                        raise HTTPException(status_code=422, detail=_error_payload("validation_error", "Validation failed.", "Fix request fields and retry."))
                    if resp.status_code >= 400:
                        raise Exception(f"remote_{resp.status_code}:{resp.text[:200]}")
                    data = resp.json()
                account_router.mark_success(account["id"])
                public_task_id = _compose_remote_public_task_id(workspace, data["task_id"])
                storage.record_operational_event(
                    "assignment_submitted",
                    task_id=public_task_id,
                    model=req.model.value,
                    lane_mode="remote",
                    value=account["id"],
                    reason=workspace,
                )
                storage.record_operational_event(
                    "generation_accepted",
                    task_id=public_task_id,
                    model=req.model.value,
                    lane_mode="remote",
                    value=round(time.monotonic() - request_started_at, 4),
                )
                if attempt > 0:
                    storage.record_operational_event(
                        "fallback_success",
                        task_id=public_task_id,
                        model=req.model.value,
                        lane_mode="remote",
                        value=attempt,
                        reason="fallback_recovered",
                    )
                _vol_commit()
                return GenerateResponse(
                    task_id=public_task_id,
                    status=TaskStatus.pending,
                )

            except NoReadyAccountError:
                remaining = _no_ready_wait_remaining(deadline)
                if not _no_ready_wait_expired(deadline):
                    await asyncio.sleep(min(1.0, remaining))
                    continue
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        **_error_payload(
                            "no_ready_accounts",
                            "No ready execution accounts are currently available.",
                            "Retry shortly.",
                        ),
                        "metadata": {
                            "waited_seconds": NO_READY_ACCOUNT_WAIT_SECONDS,
                            "tried_accounts": len(tried_accounts),
                        },
                    },
                )
            except HTTPException:
                raise
            except Exception as exc:
                last_error = str(exc)
                if tried_accounts:
                    account_router.mark_failed(tried_accounts[-1], last_error)

        if last_error:
            storage.record_operational_event("fallback_activated", model=req.model.value, lane_mode="degraded_shared" if req.type.value == "video" else None, reason=_fallback_reason_from_error(Exception(last_error)))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    **_error_payload(
                        "remote_dispatch_failed",
                        "Failed to dispatch generation to ready worker accounts.",
                        "Retry shortly.",
                    ),
                    "metadata": {
                        "tried_accounts": len(tried_accounts),
                        "last_error": last_error[:200],
                    },
                },
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_payload(
                "no_ready_accounts",
                "No ready execution accounts are currently available.",
                "Retry shortly.",
            ),
        )

    # ── Status ────────────────────────────────────────────────────────────────
    @api.get("/status/{task_id}", response_model=StatusResponse, tags=["Generation"])
    async def get_status(
        request: Request,
        task_id: str,
        resume: bool = Query(False),
        _: str = Depends(verify_generation_session),
    ):
        if resume:
            storage.record_operational_event(
                "resume_attempt",
                task_id=task_id,
            )
        if _is_remote_public_task_id(task_id):
            import httpx
            workspace, remote_task_id = _split_remote_public_task_id(task_id)
            api_key = os.environ.get("API_KEY", "")
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=5.0)) as client:
                    resp = await client.get(f"{_remote_workspace_base_url(workspace)}/status/{remote_task_id}", headers={"X-API-Key": api_key})
                    if resp.status_code == 404:
                        raise HTTPException(status_code=404, detail=_error_payload("task_not_found", "Remote task not found.", "Verify task id and retry."))
                    resp.raise_for_status()
                    raw = resp.json()
                    if not isinstance(raw, dict):
                        raw = {}

                    status_value = str(raw.get("status") or "pending")
                    progress_value = int(raw.get("progress") or 0)
                    stage_value = raw.get("stage")
                    stage_detail_value = raw.get("stage_detail")
                    error_msg_value = raw.get("error_msg")
                    diagnostics_value = raw.get("diagnostics") if isinstance(raw.get("diagnostics"), dict) else None
                    result_url, preview_url = _gateway_media_urls(request, task_id)

                    if status_value != "done":
                        result_url = None
                        preview_url = None
                    if resume:
                        storage.record_operational_event(
                            "resume_success",
                            task_id=task_id,
                            lane_mode="remote",
                            model=None,
                            reason=status_value,
                        )
                    updated_at_value = raw.get("updated_at")
                    if isinstance(updated_at_value, str):
                        try:
                            updated_at_dt = datetime.fromisoformat(updated_at_value)
                            if updated_at_dt.tzinfo is None:
                                updated_at_dt = updated_at_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
                            freshness_seconds = max(
                                0.0,
                                (datetime.now(updated_at_dt.tzinfo) - updated_at_dt).total_seconds(),
                            )
                            storage.record_operational_event(
                                "status_freshness_seconds",
                                task_id=task_id,
                                lane_mode="remote",
                                value=round(freshness_seconds, 4),
                            )
                        except Exception:
                            pass
                    _vol_commit()

                    return StatusResponse(
                        task_id=task_id,
                        status=TaskStatus(status_value),
                        progress=max(0, min(progress_value, 100)),
                        stage=stage_value,
                        stage_detail=stage_detail_value,
                        diagnostics=diagnostics_value,
                        result_url=result_url,
                        preview_url=preview_url,
                        error_msg=error_msg_value,
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=502, detail=_error_payload("remote_status_unavailable", f"Remote status fetch failed: {e}", "Retry shortly."))

        _vol_reload()
        result = storage.get_task(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail=_error_payload("task_not_found", f"Task '{task_id}' not found.", "Verify task id and retry."))

        pending_start_warning = int(os.environ.get("PENDING_WORKER_START_WARNING_SECONDS", "120"))
        pending_start_fail = int(os.environ.get("PENDING_WORKER_START_FAIL_SECONDS", "120"))
        if result.status == TaskStatus.pending and (result.progress or 0) == 0 and (result.stage is None or result.stage == "queued") and result.created_at is not None:
            age = (datetime.now(result.created_at.tzinfo) - result.created_at).total_seconds()
            if pending_start_fail > 0 and age >= pending_start_fail:
                storage.update_task_status(task_id, "failed", progress=0, error_msg="Worker start timeout: no GPU worker picked up the task in time.", stage="failed", stage_detail="worker_start_timeout")
                _vol_commit()
                result = storage.get_task(task_id) or result
            elif age >= pending_start_warning:
                result = result.model_copy(update={"stage": "queued", "stage_detail": f"Awaiting GPU worker pickup ({int(age)}s). Queue delay detected."})

        # Server-side processing stall detection
        processing_stall_timeout = int(os.environ.get("PROCESSING_STALL_TIMEOUT_SECONDS", "300"))
        if (
            result.status == TaskStatus.processing
            and result.updated_at is not None
            and processing_stall_timeout > 0
        ):
            age_since_update = (
                datetime.now(result.updated_at.tzinfo) - result.updated_at
            ).total_seconds()
            if age_since_update >= processing_stall_timeout:
                storage.update_task_status(
                    task_id,
                    "failed",
                    progress=result.progress or 0,
                    error_msg="Worker stalled: no status update for 5 minutes.",
                    stage="failed",
                    stage_detail="processing_stall_timeout",
                )
                _vol_commit()
                result = storage.get_task(task_id) or result

        if result.updated_at is not None:
            freshness_seconds = max(
                0.0,
                (datetime.now(result.updated_at.tzinfo) - result.updated_at).total_seconds(),
            )
            storage.record_operational_event(
                "status_freshness_seconds",
                task_id=task_id,
                lane_mode=result.lane_mode,
                model=None,
                value=round(freshness_seconds, 4),
            )
        if resume:
            storage.record_operational_event(
                "resume_success",
                task_id=task_id,
                lane_mode=result.lane_mode,
                model=None,
                reason=result.status.value,
            )
        _vol_commit()

        result_url, preview_url = _gateway_media_urls(request, task_id)
        if result.status == TaskStatus.done:
            result = result.model_copy(
                update={
                    "task_id": task_id,
                    "result_url": result.result_url or result_url,
                    "preview_url": result.preview_url or preview_url,
                }
            )
        else:
            result = result.model_copy(update={"task_id": task_id})
        return result

    # ── Results & Preview ─────────────────────────────────────────────────────
    @api.get("/results/{task_id}", tags=["Generation"])
    async def get_result(task_id: str, _: str = Depends(verify_generation_session)):
        if _is_remote_public_task_id(task_id):
            import httpx
            workspace, remote_task_id = _split_remote_public_task_id(task_id)
            api_key = os.environ.get("API_KEY", "")
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)) as client:
                    resp = await client.get(f"{_remote_workspace_base_url(workspace)}/results/{remote_task_id}", headers={"X-API-Key": api_key})
                    if resp.status_code == 404:
                        raise HTTPException(status_code=404, detail=_error_payload("result_not_found", "Remote result not found.", "Verify task id or regenerate."))
                    resp.raise_for_status()
                    return Response(content=resp.content, media_type=resp.headers.get("content-type", "application/octet-stream"))
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=502, detail=_error_payload("remote_result_unavailable", f"Remote result fetch failed: {exc}", "Retry shortly."))

        _vol_reload()
        task = storage.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=_error_payload("task_not_found", "Task not found.", "Verify task id and retry."))
        if task.status != TaskStatus.done:
            raise HTTPException(status_code=404, detail=_error_payload("result_not_ready", f"Task is not done yet (status: {task.status}).", "Wait for completion and retry."))

        task_row = storage.get_raw_task(task_id)
        if not task_row or not task_row.get("result_path"):
            raise HTTPException(status_code=404, detail=_error_payload("result_not_found", "Result file not found.", "Regenerate the asset."))
        fpath = task_row["result_path"]
        if not os.path.exists(fpath):
            raise HTTPException(status_code=410, detail=_error_payload("result_file_missing", "Result file missing from volume.", "Regenerate the asset."))
        ext = Path(fpath).suffix.lstrip(".")
        media_types = {"mp4": "video/mp4", "webm": "video/webm", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
        return FileResponse(fpath, media_type=media_types.get(ext, "application/octet-stream"))

    @api.get("/preview/{task_id}", tags=["Generation"])
    async def get_preview(task_id: str, _: str = Depends(verify_generation_session)):
        if _is_remote_public_task_id(task_id):
            import httpx
            workspace, remote_task_id = _split_remote_public_task_id(task_id)
            api_key = os.environ.get("API_KEY", "")
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=20.0, pool=5.0)) as client:
                    resp = await client.get(f"{_remote_workspace_base_url(workspace)}/preview/{remote_task_id}", headers={"X-API-Key": api_key})
                    if resp.status_code == 404:
                        raise HTTPException(status_code=404, detail=_error_payload("preview_not_found", "Remote preview not found.", "Verify task id or regenerate."))
                    resp.raise_for_status()
                    return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/jpeg"))
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=502, detail=_error_payload("remote_preview_unavailable", f"Remote preview fetch failed: {exc}", "Retry shortly."))

        _vol_reload()
        task_row = storage.get_raw_task(task_id)
        if not task_row:
            raise HTTPException(status_code=404, detail=_error_payload("task_not_found", "Task not found.", "Verify task id and retry."))
        preview_path = task_row.get("preview_path")
        if not preview_path or not os.path.exists(preview_path):
            raise HTTPException(status_code=404, detail=_error_payload("preview_not_ready", "Preview not available yet.", "Wait for completion and retry."))
        return FileResponse(preview_path, media_type="image/jpeg")

    # ── Gallery ───────────────────────────────────────────────────────────────
    @api.get("/gallery", response_model=GalleryResponse, tags=["Gallery"])
    async def gallery(
        request: Request,
        page: int = Query(1, ge=1),
        per_page: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
        sort: str = Query("created_at"),
        model: Optional[str] = Query(None),
        type: Optional[str] = Query(None),
        _: str = Depends(verify_generation_session),
    ):
        _vol_reload()
        items, total = storage.list_gallery(page=page, per_page=per_page, sort=sort, model_filter=model, type_filter=type)
        request_base_url = str(request.base_url).rstrip("/")
        normalized = [
            item.model_copy(update={
                "result_url": item.result_url or f"{request_base_url}/results/{item.id}",
                "preview_url": item.preview_url or f"{request_base_url}/preview/{item.id}",
            }) for item in items
        ]
        return GalleryResponse(items=normalized, total=total, page=page, per_page=per_page, has_more=(page * per_page) < total)

    @api.delete("/gallery/{task_id}", status_code=status.HTTP_200_OK, tags=["Gallery"])
    async def delete_gallery_item(task_id: str, _: str = Depends(verify_generation_session)):
        _vol_reload()
        deleted = storage.delete_gallery_item(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=_error_payload("not_found", "Gallery item not found.", "Verify item id and retry."))
        _vol_commit()
        return DeleteResponse(deleted=True, id=task_id)

    # ── Admin ─────────────────────────────────────────────────────────────────
    @api.post("/admin/login", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin"])
    async def admin_login(payload: AdminLoginRequest, request: Request, response: Response):
        verify_admin_login_password(request, payload.login, payload.password, action="admin_login")
        _vol_reload()
        token, _ = storage.create_admin_session(idle_timeout_seconds=admin_idle_timeout)
        _vol_commit()
        _set_session_cookie(response, ADMIN_SESSION_COOKIE, token, admin_idle_timeout)
        return None

    @api.post("/admin/session", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin"])
    async def create_admin_session(response: Response, _ip: str = Depends(verify_admin_key_header("admin_session_create"))):
        _vol_reload()
        token, _ = storage.create_admin_session(idle_timeout_seconds=admin_idle_timeout)
        _vol_commit()
        _set_session_cookie(response, ADMIN_SESSION_COOKIE, token, admin_idle_timeout)
        return None

    @api.get("/admin/session", response_model=AdminSessionStateResponse, tags=["Admin"])
    async def get_admin_session_state(request: Request, _ip: str = Depends(get_admin_auth("admin_session_get"))):
        token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "admin_session_missing", "detail": "Admin session is missing.", "user_action": "Login again to continue."})
        _vol_reload()
        active, reason, _ = storage.validate_admin_session(token, touch=False)
        if not active:
            code = "admin_session_expired" if reason == "expired" else "admin_session_invalid"
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": code, "detail": "Admin session is invalid or expired.", "user_action": "Login again to continue."})
        session_row = storage.get_admin_session(token)
        last_activity = None
        if session_row and session_row.get("last_activity_at"):
            try:
                last_activity = datetime.fromisoformat(session_row["last_activity_at"])
            except Exception:
                pass
        return AdminSessionStateResponse(active=True, idle_timeout_seconds=admin_idle_timeout, last_activity_at=last_activity)

    @api.delete("/admin/session", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin"])
    async def delete_admin_session(response: Response, request: Request, _ip: str = Depends(get_admin_auth("admin_session_delete"))):
        token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        if token:
            _vol_reload()
            storage.revoke_admin_session(token)
            _vol_commit()
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

    @api.get("/admin/health", tags=["Admin"])
    async def admin_health(_ip: str = Depends(get_admin_auth("health"))):
        _vol_reload()
        ready = [a for a in acc_store.list_accounts() if a["status"] == "ready"]
        return {"ok": True, "storage_ok": storage.check_storage_health(), "ready_accounts": len(ready), "diagnostics": storage.get_operational_snapshot()}

    @api.post("/admin/accounts", tags=["Admin"], status_code=201)
    async def admin_add_account(label: str = Body(...), token_id: str = Body(...), token_secret: str = Body(...), _ip: str = Depends(get_admin_auth("add_account"))):
        _vol_reload()
        missing_env = get_missing_shared_env_keys()
        if missing_env:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_error_payload(
                    "admin_env_missing",
                    "Missing required shared env: " + ", ".join(missing_env),
                    (
                        "Set required env vars (API_KEY, ADMIN_LOGIN, ADMIN_PASSWORD_HASH, "
                        "ACCOUNTS_ENCRYPT_KEY, HF_TOKEN) and restart API container."
                    ),
                ),
            )
        account_id = acc_store.add_account(label=label, token_id=token_id, token_secret=token_secret)
        _vol_commit()
        deploy_account_async(account_id)
        return {"id": account_id, "status": "pending", "message": "Deploying..."}

    @api.get("/admin/accounts", tags=["Admin"])
    async def admin_list_accounts(_ip: str = Depends(get_admin_auth("list_accounts"))):
        _vol_reload()
        return {"accounts": acc_store.list_accounts(), "diagnostics": storage.get_operational_snapshot(), "events": storage.list_operational_events(limit=30)}

    @api.delete("/admin/accounts/{account_id}", tags=["Admin"])
    async def admin_delete_account(account_id: str, _ip: str = Depends(get_admin_auth("delete_account"))):
        _vol_reload()
        if not acc_store.delete_account(account_id):
            raise HTTPException(status_code=404, detail=_error_payload("not_found", "Account not found.", "Verify account id and retry."))
        _vol_commit()
        return {"deleted": True, "id": account_id}

    @api.post("/admin/accounts/{account_id}/disable", tags=["Admin"])
    async def admin_disable_account(account_id: str, _ip: str = Depends(get_admin_auth("disable_account"))):
        _vol_reload()
        acc_store.disable_account(account_id)
        _vol_commit()
        return {"id": account_id, "status": "disabled"}

    @api.post("/admin/accounts/{account_id}/enable", tags=["Admin"])
    async def admin_enable_account(account_id: str, _ip: str = Depends(get_admin_auth("enable_account"))):
        _vol_reload()
        if acc_store.get_account(account_id) is None:
            raise HTTPException(status_code=404, detail=_error_payload("not_found", "Account not found.", "Verify account id and retry."))
        acc_store.enable_account(account_id)
        _vol_commit()
        return {"id": account_id, "status": "ready", "message": "Account enabled and returned to rotation."}

    @api.post("/admin/accounts/{account_id}/deploy", tags=["Admin"])
    async def admin_deploy_account(account_id: str, _ip: str = Depends(get_admin_auth("deploy_account"))):
        if acc_store.get_account(account_id) is None:
            raise HTTPException(status_code=404, detail=_error_payload("not_found", "Account not found.", "Verify account id and retry."))
        deploy_account_async(account_id)
        return {"id": account_id, "status": "checking", "message": "Deploy started, health-check in progress."}

    @api.post("/admin/deploy-all", tags=["Admin"])
    async def admin_deploy_all(_ip: str = Depends(get_admin_auth("deploy_all"))):
        threads = deploy_all_accounts()
        return {"deploying": len(threads), "message": f"Deploying {len(threads)} account(s)..."}

    @api.post("/admin/accounts/{account_id}/warmup", tags=["Admin"])
    async def admin_warmup_account(
        account_id: str,
        payload: dict[str, Any] = Body(default={}),
        _ip: str = Depends(get_admin_auth("warmup_account")),
    ):
        _vol_reload()
        account = _find_account_public(account_id)
        if account is None:
            raise HTTPException(status_code=404, detail=_error_payload("not_found", "Account not found.", "Verify account id and retry."))
        models = _parse_warmup_models(payload.get("models"))
        mode = _parse_warmup_mode(payload.get("mode", "best_effort"))
        force = bool(payload.get("force", False))
        ttl_seconds = _parse_positive_int(payload.get("ttl_seconds"), WARMUP_TTL_SECONDS, "ttl_seconds")
        cooldown_seconds = _parse_positive_int(payload.get("cooldown_seconds"), WARMUP_COOLDOWN_SECONDS, "cooldown_seconds")

        run_id = acc_store.create_warmup_run(
            triggered_by="admin",
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
        _vol_commit()
        return {"run_id": run_id, "status": status_value, **summary}

    @api.post("/admin/warmup", tags=["Admin"])
    async def admin_warmup_batch(
        payload: dict[str, Any] = Body(default={}),
        _ip: str = Depends(get_admin_auth("warmup_batch")),
    ):
        _vol_reload()
        all_accounts = acc_store.list_accounts()
        filter_ids = payload.get("account_ids")
        if filter_ids is not None and not isinstance(filter_ids, list):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_error_payload("validation_error", "account_ids must be an array.", "Provide a valid account_ids array."),
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
            triggered_by="admin",
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
        _vol_commit()
        return {"run_id": run_id, "status": status_value, **summary}

    @api.get("/admin/warmup-runs/{run_id}", tags=["Admin"])
    async def admin_warmup_run_status(
        run_id: str,
        _ip: str = Depends(get_admin_auth("warmup_run_status")),
    ):
        _vol_reload()
        run = acc_store.get_warmup_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=_error_payload("not_found", "Warmup run not found.", "Verify run id and retry."))
        items = acc_store.list_warmup_items(run_id)
        return {"run": run, "items": items}

    @api.get("/admin/logs", tags=["Admin"])
    async def admin_get_logs(limit: int = 100, _ip: str = Depends(get_admin_auth("read_logs"))):
        _vol_reload()
        return {"logs": storage.get_audit_logs(limit=limit)}

    return api
