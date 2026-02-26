"""
Security helpers for admin endpoints:
- Rate-limiting with in-memory sliding window
- Audit log writes to SQLite
- Constant-time key comparison
- Minimum key length enforcement
"""
from __future__ import annotations

import hmac
import logging
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException, Header, Request, status

logger = logging.getLogger("admin_security")

_rate_windows: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()
RATE_LIMIT = 30
RATE_WINDOW = 60.0
ADMIN_SESSION_COOKIE = "gg_admin_session"
ADMIN_IDLE_TIMEOUT_SECONDS = 12 * 3600


def _admin_error(
    *,
    code: str,
    detail: str,
    user_action: str,
    status_code: int = status.HTTP_401_UNAUTHORIZED,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "detail": detail, "user_action": user_action},
    )


def _rate_check(ip: str) -> None:
    now = time.monotonic()
    with _rate_lock:
        buckets = _rate_windows[ip]
        _rate_windows[ip] = [t for t in buckets if now - t < RATE_WINDOW]
        if len(_rate_windows[ip]) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Too many admin requests. Try again later.")
        _rate_windows[ip].append(now)


def _get_db_path() -> str:
    try:
        from config import DB_PATH
        return DB_PATH
    except ImportError:
        return "/results/gallery.db"


def _ensure_audit_table() -> None:
    try:
        conn = sqlite3.connect(_get_db_path())
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ts       TEXT NOT NULL,
                ip       TEXT,
                action   TEXT NOT NULL,
                details  TEXT,
                success  INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("Could not create audit table: %s", exc)


def _log_action(ip: str, action: str, details: str = "", success: bool = True) -> None:
    try:
        conn = sqlite3.connect(_get_db_path())
        conn.execute(
            "INSERT INTO admin_audit_log(ts,ip,action,details,success) VALUES(?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), ip, action, details, int(success)),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("Audit log write failed: %s", exc)


def _get_client_ip(request: Request) -> str:
    # Prefer first client IP from X-Forwarded-For if present.
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def get_admin_auth(action: str = "unknown"):
    """
    Returns a FastAPI dependency that validates x-admin-key.
    Usage: Depends(get_admin_auth("list_accounts"))
    """
    import os as _os

    async def _dep(request: Request, x_admin_key: str = Header("", alias="x-admin-key")) -> str:
        ip = _get_client_ip(request)

        _rate_check(ip)

        expected = _os.environ.get("ADMIN_KEY", "")

        if expected and len(expected) < 16:
            logger.error("ADMIN_KEY is too short (<%d chars)", 16)
            _log_action(ip, action, "key_too_short", success=False)
            raise _admin_error(
                code="admin_misconfigured",
                detail="Admin key is configured with invalid length.",
                user_action="Contact support and rotate ADMIN_KEY.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not expected:
            _log_action(ip, action, "no_key_configured", success=False)
            raise _admin_error(
                code="admin_misconfigured",
                detail="Admin is not configured.",
                user_action="Configure ADMIN_KEY in backend secrets.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # Backward-compatible path: explicit header auth.
        if x_admin_key:
            if not hmac.compare_digest(x_admin_key.encode(), expected.encode()):
                _log_action(ip, action, "bad_key_attempt", success=False)
                logger.warning("Admin auth failure for action=%s ip=%s", action, ip)
                raise _admin_error(
                    code="admin_key_invalid",
                    detail="Invalid admin key.",
                    user_action="Re-enter admin key and retry.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            _log_action(ip, action, "auth=header", success=True)
            return ip

        # Preferred path: admin session cookie.
        token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        if not token:
            _log_action(ip, action, "missing_admin_session", success=False)
            raise _admin_error(
                code="admin_session_missing",
                detail="Admin session is missing.",
                user_action="Login again to continue.",
            )

        import storage

        active, reason, _ = storage.validate_admin_session(token, touch=True)
        if not active:
            _log_action(ip, action, f"invalid_admin_session:{reason}", success=False)
            raise _admin_error(
                code="admin_session_expired" if reason == "expired" else "admin_session_invalid",
                detail="Admin session is invalid or expired.",
                user_action="Login again to continue.",
            )

        _log_action(ip, action, "auth=cookie", success=True)
        return ip

    return _dep


def verify_admin_key_header(action: str = "admin_session_create"):
    """
    Strict header-based admin auth dependency.
    Used for POST /admin/session.
    """

    async def _dep(request: Request, x_admin_key: str = Header("", alias="x-admin-key")) -> str:
        ip = _get_client_ip(request)
        _rate_check(ip)

        import os as _os

        expected = _os.environ.get("ADMIN_KEY", "")
        if not expected:
            _log_action(ip, action, "no_key_configured", success=False)
            raise _admin_error(
                code="admin_misconfigured",
                detail="Admin is not configured.",
                user_action="Configure ADMIN_KEY in backend secrets.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not x_admin_key or not hmac.compare_digest(x_admin_key.encode(), expected.encode()):
            _log_action(ip, action, "bad_key_attempt", success=False)
            raise _admin_error(
                code="admin_key_invalid",
                detail="Invalid admin key.",
                user_action="Check admin key and retry.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        _log_action(ip, action, "auth=header", success=True)
        return ip

    return _dep
