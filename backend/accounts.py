"""
Modal account management backed by SQLite.

Credentials are encrypted at rest using Fernet key from ACCOUNTS_ENCRYPT_KEY.
"""
from __future__ import annotations

import os
import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from config import DB_PATH, RESULTS_PATH

_lock = threading.Lock()
_ENC_PREFIX = "enc::"
logger = logging.getLogger("accounts")

_ALLOWED_STATUSES = {"pending", "checking", "ready", "failed", "disabled"}
_ALLOWED_TRANSITIONS = {
    "pending": {"pending", "checking", "failed", "disabled"},
    "checking": {"checking", "ready", "failed", "disabled"},
    "ready": {"ready", "checking", "failed", "disabled"},
    "failed": {"failed", "checking", "disabled"},
    "disabled": {"disabled", "ready", "checking"},
}

# ── Error classification ────────────────────────────────────────────────────
_QUOTA_PATTERNS = ("quota", "limit exceeded", "insufficient credits", "rate limit")
_AUTH_PATTERNS = ("authentication", "unauthorized", "invalid token", "auth failed")
_TIMEOUT_PATTERNS = ("timeout", "timed out")
_CONTAINER_PATTERNS = ("container", "deployment failed")
_HEALTH_PATTERNS = ("health check", "endpoint not responding")
_CONFIG_PATTERNS = ("secret sync failed", "missing required shared env", "config_failed")


def _classify_error(error: str) -> tuple[str, str]:
    """
    Classify an error message into (failure_type, recovery_policy).

    Returns:
        tuple of (failure_type, recovery_policy) where:
        - failure_type: quota_exceeded | auth_failed | config_failed | timeout | container_failed | health_check_failed | unknown
        - recovery_policy: manual_only | auto_recover
    """
    lower = error.lower()
    if any(p in lower for p in _QUOTA_PATTERNS):
        return "quota_exceeded", "manual_only"
    if any(p in lower for p in _AUTH_PATTERNS):
        return "auth_failed", "manual_only"
    if any(p in lower for p in _CONFIG_PATTERNS):
        return "config_failed", "manual_only"
    if any(p in lower for p in _TIMEOUT_PATTERNS):
        return "timeout", "auto_recover"
    if any(p in lower for p in _CONTAINER_PATTERNS):
        return "container_failed", "auto_recover"
    if any(p in lower for p in _HEALTH_PATTERNS):
        return "health_check_failed", "auto_recover"
    return "unknown", "auto_recover"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_cipher() -> Fernet:
    raw = os.environ.get("ACCOUNTS_ENCRYPT_KEY", "").strip()
    if not raw:
        raise RuntimeError("ACCOUNTS_ENCRYPT_KEY is not configured")
    return Fernet(raw.encode())


def _encrypt_secret(secret: str) -> str:
    token = _get_cipher().encrypt(secret.encode("utf-8")).decode("utf-8")
    return f"{_ENC_PREFIX}{token}"


def _decrypt_secret(value: str) -> str:
    # Backward compatibility for legacy plaintext rows.
    if not value.startswith(_ENC_PREFIX):
        return value
    token = value[len(_ENC_PREFIX):]
    try:
        return _get_cipher().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError("Failed to decrypt account token_secret") from exc


def _to_public(row: sqlite3.Row) -> dict:
    data = dict(row)
    data.pop("token_id", None)
    data.pop("token_secret", None)
    return data


def _to_internal(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["token_secret"] = _decrypt_secret(data["token_secret"])
    return data


@contextmanager
def _db():
    os.makedirs(RESULTS_PATH, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_accounts_table() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS modal_accounts (
                id                  TEXT PRIMARY KEY,
                label               TEXT NOT NULL,
                token_id            TEXT NOT NULL,
                token_secret        TEXT NOT NULL,
                workspace           TEXT,
                status              TEXT NOT NULL DEFAULT 'pending',
                added_at            TEXT NOT NULL,
                last_used           TEXT,
                last_error          TEXT,
                use_count           INTEGER NOT NULL DEFAULT 0,
                failed_at           TEXT,
                fail_count          INTEGER NOT NULL DEFAULT 0,
                failure_type        TEXT,
                last_health_check   TEXT,
                health_check_result TEXT
            )
            """
        )
        for ddl in (
            "ALTER TABLE modal_accounts ADD COLUMN failed_at TEXT",
            "ALTER TABLE modal_accounts ADD COLUMN fail_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE modal_accounts ADD COLUMN failure_type TEXT",
            "ALTER TABLE modal_accounts ADD COLUMN last_health_check TEXT",
            "ALTER TABLE modal_accounts ADD COLUMN health_check_result TEXT",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                # Column already exists on upgraded databases.
                pass


def add_account(
    label: str,
    token_id: str,
    token_secret: str,
) -> str:
    """Insert a new account in 'pending' state. Returns account ID."""
    account_id = str(uuid.uuid4())
    now = _now_iso()
    enc_secret = _encrypt_secret(token_secret)
    with _lock, _db() as conn:
        conn.execute(
            """
            INSERT INTO modal_accounts
              (id, label, token_id, token_secret, status, added_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (account_id, label, token_id, enc_secret, now),
        )
    return account_id


def get_account(account_id: str) -> Optional[dict]:
    """
    Return account with decrypted secrets for internal backend usage
    (deployer / dispatch only).
    """
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM modal_accounts WHERE id=?", (account_id,)
        ).fetchone()
    return _to_internal(row) if row else None


def list_accounts() -> list[dict]:
    """Return account list safe for admin API responses (no secrets)."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM modal_accounts ORDER BY added_at DESC"
        ).fetchall()
    return [_to_public(r) for r in rows]


def list_ready_accounts() -> list[dict]:
    """
    Return ready accounts for router usage.
    Returns public data only — secrets are NOT included.
    Credentials are fetched on-demand via get_account() when needed for deploy.
    """
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM modal_accounts WHERE status='ready' ORDER BY use_count ASC, last_used ASC"
        ).fetchall()
    return [_to_public(r) for r in rows]


def update_account_status(
    account_id: str,
    status: str,
    workspace: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    if status not in _ALLOWED_STATUSES:
        raise ValueError(f"Unknown account status: {status}")

    fields = ["status = ?", "last_error = ?"]
    values: list = [status, error]
    if workspace is not None:
        fields.append("workspace = ?")
        values.append(workspace)
    if status == "ready":
        # Successful readiness clears failure metadata.
        values[1] = None
        fields.append("failed_at = NULL")
    values.append(account_id)

    with _lock, _db() as conn:
        row = conn.execute(
            "SELECT status FROM modal_accounts WHERE id=?",
            (account_id,),
        ).fetchone()
        if row is None:
            return
        prev_status = row["status"]
        allowed = _ALLOWED_TRANSITIONS.get(prev_status, {prev_status})
        if status not in allowed:
            raise ValueError(
                f"Forbidden account status transition: {prev_status} -> {status}"
            )

        conn.execute(
            f"UPDATE modal_accounts SET {', '.join(fields)} WHERE id=?",
            values,
        )
        logger.info(
            "account_status_transition account_id=%s prev=%s new=%s workspace=%s error=%s",
            account_id,
            prev_status,
            status,
            workspace,
            error,
        )


def mark_account_failed(
    account_id: str,
    error: str,
    max_fail_count: int = 6,
    failure_type: Optional[str] = None,
) -> None:
    """
    Mark account failed and increment failure counter.

    Error classification:
    - quota_exceeded / auth_failed / config_failed → immediately disabled (manual_only)
    - timeout / container_failed / health_check_failed / unknown → fail_count logic (auto_recover)

    If fail_count reaches max_fail_count for auto_recover errors,
    account is disabled automatically.
    """
    if failure_type is None:
        failure_type, _ = _classify_error(error)

    recovery_policy = (
        "manual_only"
        if failure_type in ("quota_exceeded", "auth_failed", "config_failed")
        else "auto_recover"
    )

    now = _now_iso()
    with _lock, _db() as conn:
        row = conn.execute(
            "SELECT status, fail_count FROM modal_accounts WHERE id=?",
            (account_id,),
        ).fetchone()
        if row is None:
            return

        prev_status = row["status"]
        prev_fail_count = int(row["fail_count"] or 0)

        if recovery_policy == "manual_only":
            # Quota / auth errors → immediately disable
            next_status = "disabled"
            new_fail_count = prev_fail_count + 1
        else:
            # Temporary errors → fail_count threshold logic
            new_fail_count = prev_fail_count + 1
            next_status = "disabled" if new_fail_count >= max_fail_count else "failed"

        conn.execute(
            """
            UPDATE modal_accounts
            SET status=?, last_error=?, failed_at=?, fail_count=?, failure_type=?
            WHERE id=?
            """,
            (next_status, error, now, new_fail_count, failure_type, account_id),
        )
        logger.warning(
            "account_mark_failed account_id=%s prev=%s new=%s fail_count=%s failure_type=%s error=%s",
            account_id,
            prev_status,
            next_status,
            new_fail_count,
            failure_type,
            error,
        )


def recover_failed_accounts(cooldown_seconds: int = 300) -> int:
    """
    Auto-recover failed accounts after cooldown to avoid permanent brick state.
    Returns number of recovered accounts.

    Accounts with failure_type in ('quota_exceeded', 'auth_failed', 'config_failed') are excluded
    from auto-recovery — they require manual intervention via enable_account().
    """
    if cooldown_seconds <= 0:
        return 0

    threshold = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
    recovered = 0

    with _lock, _db() as conn:
        rows = conn.execute(
            """
            SELECT id, failed_at, failure_type
            FROM modal_accounts
            WHERE status='failed'
              AND failed_at IS NOT NULL
              AND (failure_type IS NULL OR failure_type NOT IN ('quota_exceeded', 'auth_failed', 'config_failed'))
            """
        ).fetchall()

        for row in rows:
            failed_at_raw = row["failed_at"]
            try:
                failed_at = datetime.fromisoformat(failed_at_raw)
                if failed_at.tzinfo is None:
                    failed_at = failed_at.replace(tzinfo=timezone.utc)
            except Exception:
                # If timestamp is malformed, recover immediately.
                failed_at = threshold - timedelta(seconds=1)

            if failed_at <= threshold:
                conn.execute(
                    """
                    UPDATE modal_accounts
                    SET status='ready', last_error=NULL, failed_at=NULL, failure_type=NULL
                    WHERE id=?
                    """,
                    (row["id"],),
                )
                recovered += 1

    if recovered:
        logger.info("recovered_failed_accounts count=%s cooldown_seconds=%s", recovered, cooldown_seconds)
    return recovered


def mark_account_used(account_id: str) -> None:
    with _lock, _db() as conn:
        conn.execute(
            """
            UPDATE modal_accounts
            SET last_used=?, use_count=use_count+1
            WHERE id=?
            """,
            (_now_iso(), account_id),
        )


def delete_account(account_id: str) -> bool:
    with _lock, _db() as conn:
        cursor = conn.execute(
            "DELETE FROM modal_accounts WHERE id=?", (account_id,)
        )
    return cursor.rowcount > 0


def disable_account(account_id: str) -> None:
    update_account_status(account_id, "disabled")


def enable_account(account_id: str) -> None:
    """Re-enable a disabled account, clearing failure metadata."""
    with _lock, _db() as conn:
        row = conn.execute(
            "SELECT status FROM modal_accounts WHERE id=?", (account_id,)
        ).fetchone()
        if row is None:
            return
        conn.execute(
            """
            UPDATE modal_accounts
            SET status='ready', last_error=NULL, failed_at=NULL, failure_type=NULL, fail_count=0
            WHERE id=?
            """,
            (account_id,),
        )
        logger.info(
            "account_enabled account_id=%s prev=%s new=ready",
            account_id, row["status"],
        )


def update_health_check(
    account_id: str,
    result: str,
) -> None:
    """Cache health check result for an account."""
    now = _now_iso()
    with _lock, _db() as conn:
        conn.execute(
            """
            UPDATE modal_accounts
            SET last_health_check=?, health_check_result=?
            WHERE id=?
            """,
            (now, result, account_id),
        )
