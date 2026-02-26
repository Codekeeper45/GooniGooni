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
                id           TEXT PRIMARY KEY,
                label        TEXT NOT NULL,
                token_id     TEXT NOT NULL,
                token_secret TEXT NOT NULL,
                workspace    TEXT,
                status       TEXT NOT NULL DEFAULT 'pending',
                added_at     TEXT NOT NULL,
                last_used    TEXT,
                last_error   TEXT,
                use_count    INTEGER NOT NULL DEFAULT 0,
                failed_at    TEXT,
                fail_count   INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        for ddl in (
            "ALTER TABLE modal_accounts ADD COLUMN failed_at TEXT",
            "ALTER TABLE modal_accounts ADD COLUMN fail_count INTEGER NOT NULL DEFAULT 0",
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


def mark_account_failed(account_id: str, error: str, max_fail_count: int = 6) -> None:
    """
    Mark account failed and increment failure counter.
    If fail_count reaches max_fail_count, account is disabled automatically.
    """
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
        new_fail_count = prev_fail_count + 1
        next_status = "disabled" if new_fail_count >= max_fail_count else "failed"

        conn.execute(
            """
            UPDATE modal_accounts
            SET status=?, last_error=?, failed_at=?, fail_count=?
            WHERE id=?
            """,
            (next_status, error, now, new_fail_count, account_id),
        )
        logger.warning(
            "account_mark_failed account_id=%s prev=%s new=%s fail_count=%s error=%s",
            account_id,
            prev_status,
            next_status,
            new_fail_count,
            error,
        )


def recover_failed_accounts(cooldown_seconds: int = 300) -> int:
    """
    Auto-recover failed accounts after cooldown to avoid permanent brick state.
    Returns number of recovered accounts.
    """
    if cooldown_seconds <= 0:
        return 0

    threshold = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
    recovered = 0

    with _lock, _db() as conn:
        rows = conn.execute(
            """
            SELECT id, failed_at
            FROM modal_accounts
            WHERE status='failed' AND failed_at IS NOT NULL
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
                    SET status='ready', last_error=NULL, failed_at=NULL
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
    update_account_status(account_id, "ready", error=None)
