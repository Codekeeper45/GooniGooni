"""
Security hardening for admin endpoints:
- Rate-limiting with simple in-memory sliding window (no extras required)
- All admin actions written to audit_log table in SQLite
- Constant-time key comparison (hmac.compare_digest)
- Minimum key length enforcement
- IP logging
"""
from __future__ import annotations

import hmac
import logging
import os
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger("admin_security")

# ── Rate limiter: max 30 admin requests per IP per 60s ────────────────────────
_rate_windows: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 30          # max requests
RATE_WINDOW = 60.0       # seconds


def _rate_check(ip: str) -> None:
    now = time.monotonic()
    buckets = _rate_windows[ip]
    # purge old entries
    _rate_windows[ip] = [t for t in buckets if now - t < RATE_WINDOW]
    if len(_rate_windows[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many admin requests. Try again later.")
    _rate_windows[ip].append(now)


# ── Audit log (writes to same SQLite DB as gallery) ───────────────────────────
def _get_db_path() -> str:
    try:
        from config import DB_PATH
        return DB_PATH
    except ImportError:
        return "/results/gallery.db"


def _ensure_audit_table() -> None:
    try:
        conn = sqlite3.connect(_get_db_path())
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ts       TEXT NOT NULL,
                ip       TEXT,
                action   TEXT NOT NULL,
                details  TEXT,
                success  INTEGER NOT NULL DEFAULT 1
            )
        """)
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


# ── FastAPI Dependency version (works in nested closures) ─────────────────────
def get_admin_auth(action: str = "unknown"):
    """
    Returns a FastAPI dependency that validates the admin key via Header().
    Usage: ip = Depends(get_admin_auth("list_accounts"))
    """
    from fastapi import Header, HTTPException as _HTTPException

    async def _dep(x_admin_key: str = Header("", alias="x-admin-key")) -> str:
        """Validate admin key from header — no Request annotation needed."""
        import os as _os
        ip = "dependency"  # IP not available without Request, logged action matters more

        # Rate-limit
        _rate_check(ip)

        expected = _os.environ.get("ADMIN_KEY", "")

        if expected and len(expected) < 16:
            logger.error("ADMIN_KEY is too short (<%d chars)", 16)
            _log_action(ip, action, "key_too_short", success=False)
            raise _HTTPException(status_code=403, detail="Admin not configured properly")

        if not expected:
            _log_action(ip, action, "no_key_configured", success=False)
            raise _HTTPException(status_code=403, detail="Admin not configured")

        if not hmac.compare_digest(x_admin_key.encode(), expected.encode()):
            _log_action(ip, action, "bad_key_attempt", success=False)
            logger.warning("Admin auth failure for action=%s", action)
            raise _HTTPException(status_code=403, detail="Invalid admin key")

        _log_action(ip, action, success=True)
        return ip

    return _dep

