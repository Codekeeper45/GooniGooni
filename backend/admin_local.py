"""
Local admin API for VM deployment.

This service is intentionally limited to admin/auth/account operations so that
admin login does not depend on Modal webhook availability or billing state.
"""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response, status
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
from deployer import deploy_account_async, deploy_all_accounts
from schemas import AdminLoginRequest, AdminSessionStateResponse


def _error_payload(*, code: str, detail: str, user_action: str) -> dict:
    return {"code": code, "detail": detail, "user_action": user_action}


admin_idle_timeout_seconds = int(os.environ.get("ADMIN_IDLE_TIMEOUT_SECONDS", str(ADMIN_IDLE_TIMEOUT_SECONDS)))
admin_cookie_secure = os.environ.get("ADMIN_COOKIE_SECURE", "0") == "1"
admin_cookie_samesite = (os.environ.get("ADMIN_COOKIE_SAMESITE", "lax") or "lax").lower()
if admin_cookie_samesite not in {"none", "lax", "strict"}:
    admin_cookie_samesite = "lax"
if admin_cookie_samesite == "none" and not admin_cookie_secure:
    # SameSite=None requires Secure in modern browsers.
    admin_cookie_samesite = "lax"

api = FastAPI(
    title="Gooni Local Admin API",
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
