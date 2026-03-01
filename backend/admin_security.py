"""
Security helpers for admin endpoints:
- Rate-limiting with SQLite-backed sliding window (shared across workers)
- Audit log writes to SQLite
- Constant-time key comparison
- Minimum key length enforcement
"""
from __future__ import annotations

import hmac
import hashlib
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone

from fastapi import HTTPException, Header, Request, status

logger = logging.getLogger("admin_security")

_rate_lock = threading.Lock()
RATE_WINDOW = 60.0
RATE_LIMIT_AUTH = 20
RATE_LIMIT_LOGIN_FAILURE = RATE_LIMIT_AUTH
RATE_LIMIT_WRITE = 30
RATE_LIMIT_READ = 60
RATE_LIMIT_SESSION_READ = 120
ADMIN_SESSION_COOKIE = "gg_admin_session"
ADMIN_IDLE_TIMEOUT_SECONDS = 12 * 3600


def _reload_results_volume() -> None:
    """Best-effort volume reload before SQLite reads."""
    try:
        import modal

        modal.Volume.from_name("results").reload()
    except Exception:
        pass


def _admin_error(
    *,
    code: str,
    detail: str,
    user_action: str,
    status_code: int = status.HTTP_401_UNAUTHORIZED,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "detail": detail, "user_action": user_action},
        headers=headers,
    )


def _verify_pbkdf2_sha256(password: str, stored_hash: str) -> bool:
    """
    Verify hash format: pbkdf2_sha256$<iterations>$<salt>$<hex_digest>
    """
    try:
        scheme, iterations_raw, salt, expected_hex = stored_hash.split("$", 3)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iterations_raw)
    except ValueError:
        return False
    if iterations < 100_000 or iterations > 10_000_000:
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(derived, expected_hex)


def _verify_admin_password(password: str, stored_hash: str) -> bool:
    """
    Verify admin password against configured hash.
    Supported formats:
      - pbkdf2_sha256$<iterations>$<salt>$<hex_digest>
      - bcrypt ($2a/$2b/$2y) when bcrypt is installed
    """
    if not stored_hash:
        return False
    if stored_hash.startswith("pbkdf2_sha256$"):
        return _verify_pbkdf2_sha256(password, stored_hash)
    if stored_hash.startswith("$2a$") or stored_hash.startswith("$2b$") or stored_hash.startswith("$2y$"):
        try:
            import bcrypt
        except Exception:
            return False
        try:
            return bool(bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")))
        except Exception:
            return False
    return False


def _ensure_rate_limit_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            action_bucket TEXT NOT NULL DEFAULT 'admin_read',
            ts REAL NOT NULL
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(admin_rate_limits)").fetchall()}
    if "action_bucket" not in columns:
        conn.execute(
            "ALTER TABLE admin_rate_limits ADD COLUMN action_bucket TEXT NOT NULL DEFAULT 'admin_read'"
        )
    if "outcome" not in columns:
        conn.execute(
            "ALTER TABLE admin_rate_limits ADD COLUMN outcome TEXT NOT NULL DEFAULT 'attempt'"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_rate_limits_ip_bucket_ts ON admin_rate_limits(ip, action_bucket, ts)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_rate_limits_ip_bucket_outcome_ts ON admin_rate_limits(ip, action_bucket, outcome, ts)"
    )


def _clear_rate_limit_state_for_tests() -> None:
    """
    Test-only helper for deterministic rate-limit assertions.
    Production code does not call this function.
    """
    try:
        conn = sqlite3.connect(_get_db_path())
        conn.execute("DELETE FROM admin_rate_limits")
        conn.commit()
        conn.close()
    except Exception:
        pass


def _rate_bucket_and_limit(action: str) -> tuple[str, int]:
    action_l = (action or "").lower()
    if "admin_session_get" in action_l:
        return "admin_session_read", RATE_LIMIT_SESSION_READ
    if "admin_login" in action_l:
        return "admin_login_attempt", RATE_LIMIT_AUTH
    if "admin_session_create" in action_l:
        return "admin_session_create", RATE_LIMIT_AUTH
    if any(token in action_l for token in ("admin_session_delete",)):
        return "admin_write", RATE_LIMIT_WRITE
    if any(token in action_l for token in ("disable_account", "enable_account")):
        return "admin_write", RATE_LIMIT_WRITE
    if any(
        token in action_l
        for token in (
            "add_account",
            "delete_account",
            "deploy",
        )
    ):
        return "admin_write", RATE_LIMIT_WRITE
    return "admin_read", RATE_LIMIT_READ


def _rate_check(ip: str, *, action: str = "unknown") -> None:
    now = time.time()
    threshold = now - RATE_WINDOW
    bucket, limit = _rate_bucket_and_limit(action)
    with _rate_lock:
        conn = sqlite3.connect(_get_db_path(), timeout=5.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            _ensure_rate_limit_table(conn)
            conn.execute("DELETE FROM admin_rate_limits WHERE ts < ?", (threshold,))
            current_hits = conn.execute(
                "SELECT COUNT(*) FROM admin_rate_limits WHERE ip=? AND action_bucket=? AND ts>=?",
                (ip, bucket, threshold),
            ).fetchone()[0]
            if current_hits >= limit:
                oldest_ts = conn.execute(
                    "SELECT MIN(ts) FROM admin_rate_limits WHERE ip=? AND action_bucket=? AND ts>=?",
                    (ip, bucket, threshold),
                ).fetchone()[0]
                retry_after = 1
                if oldest_ts is not None:
                    retry_after = max(1, int((oldest_ts + RATE_WINDOW) - now) + 1)
                conn.commit()
                raise _admin_error(
                    code="admin_rate_limited",
                    detail="Too many admin requests. Try again later.",
                    user_action="Wait a minute and retry.",
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
            conn.execute(
                "INSERT INTO admin_rate_limits(ip, action_bucket, ts, outcome) VALUES(?, ?, ?, ?)",
                (ip, bucket, now, "attempt"),
            )
            conn.commit()
        finally:
            conn.close()


def _rate_check_admin_login_failures(ip: str) -> None:
    now = time.time()
    threshold = now - RATE_WINDOW
    with _rate_lock:
        conn = sqlite3.connect(_get_db_path(), timeout=5.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            _ensure_rate_limit_table(conn)
            conn.execute("DELETE FROM admin_rate_limits WHERE ts < ?", (threshold,))
            failures = conn.execute(
                """
                SELECT COUNT(*) FROM admin_rate_limits
                WHERE ip=? AND action_bucket='admin_login_attempt' AND outcome='failure' AND ts>=?
                """,
                (ip, threshold),
            ).fetchone()[0]
            if failures >= RATE_LIMIT_LOGIN_FAILURE:
                oldest_ts = conn.execute(
                    """
                    SELECT MIN(ts) FROM admin_rate_limits
                    WHERE ip=? AND action_bucket='admin_login_attempt' AND outcome='failure' AND ts>=?
                    """,
                    (ip, threshold),
                ).fetchone()[0]
                retry_after = 1
                if oldest_ts is not None:
                    retry_after = max(1, int((oldest_ts + RATE_WINDOW) - now) + 1)
                conn.commit()
                raise _admin_error(
                    code="admin_login_rate_limited",
                    detail="Too many failed admin login attempts. Try again later.",
                    user_action="Wait a minute and retry.",
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
            conn.commit()
        finally:
            conn.close()


def _record_admin_login_attempt(ip: str, *, success: bool) -> None:
    now = time.time()
    threshold = now - RATE_WINDOW
    outcome = "success" if success else "failure"
    with _rate_lock:
        conn = sqlite3.connect(_get_db_path(), timeout=5.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            _ensure_rate_limit_table(conn)
            conn.execute("DELETE FROM admin_rate_limits WHERE ts < ?", (threshold,))
            conn.execute(
                "INSERT INTO admin_rate_limits(ip, action_bucket, ts, outcome) VALUES(?, 'admin_login_attempt', ?, ?)",
                (ip, now, outcome),
            )
            if success:
                conn.execute(
                    """
                    DELETE FROM admin_rate_limits
                    WHERE ip=? AND action_bucket='admin_login_attempt' AND outcome='failure' AND ts>=?
                    """,
                    (ip, threshold),
                )
            conn.commit()
        finally:
            conn.close()


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

        _rate_check(ip, action=action)

        expected = _os.environ.get("ADMIN_KEY", "")
        # Backward-compatible path: explicit header auth.
        # This path still requires ADMIN_KEY.
        if x_admin_key:
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
                _log_action(ip, action, "no_key_configured_for_header_auth", success=False)
                raise _admin_error(
                    code="admin_misconfigured",
                    detail="Header-based admin key auth is not configured.",
                    user_action="Configure ADMIN_KEY or use login/password session.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
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
        # This path does NOT depend on ADMIN_KEY and supports login/password mode.
        token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        if not token:
            _log_action(ip, action, "missing_admin_session", success=False)
            raise _admin_error(
                code="admin_session_missing",
                detail="Admin session is missing.",
                user_action="Login again to continue.",
            )

        import storage

        _reload_results_volume()
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
        _rate_check(ip, action=action)

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


def verify_admin_login_password(request: Request, login: str, password: str, action: str = "admin_login") -> str:
    """
    Validate admin login/password against env-configured credentials.
    Required env:
      - ADMIN_LOGIN
      - ADMIN_PASSWORD_HASH
    """
    import os as _os

    ip = _get_client_ip(request)

    expected_login = _os.environ.get("ADMIN_LOGIN", "")
    expected_password_hash = _os.environ.get("ADMIN_PASSWORD_HASH", "")

    if not expected_login:
        _log_action(ip, action, "admin_login_misconfigured", success=False)
        raise _admin_error(
            code="admin_misconfigured",
            detail="Admin login is not configured.",
            user_action="Configure ADMIN_LOGIN and ADMIN_PASSWORD_HASH in backend secrets.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if not expected_password_hash:
        _log_action(ip, action, "admin_password_misconfigured", success=False)
        raise _admin_error(
            code="admin_misconfigured",
            detail="Admin password hash is not configured.",
            user_action="Configure ADMIN_PASSWORD_HASH in backend secrets.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if not login or not password:
        _rate_check_admin_login_failures(ip)
        _record_admin_login_attempt(ip, success=False)
        _log_action(ip, action, "empty_credentials", success=False)
        raise _admin_error(
            code="admin_credentials_invalid",
            detail="Invalid admin credentials.",
            user_action="Check login and password, then retry.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    login_ok = hmac.compare_digest(login.encode("utf-8"), expected_login.encode("utf-8"))
    password_ok = _verify_admin_password(password, expected_password_hash)
    if login_ok and password_ok:
        _record_admin_login_attempt(ip, success=True)
        _log_action(ip, action, "auth=login_password", success=True)
        return ip

    _rate_check_admin_login_failures(ip)
    _record_admin_login_attempt(ip, success=False)
    _log_action(ip, action, "bad_login_password", success=False)
    raise _admin_error(
        code="admin_credentials_invalid",
        detail="Invalid admin credentials.",
        user_action="Check login and password, then retry.",
        status_code=status.HTTP_403_FORBIDDEN,
    )
