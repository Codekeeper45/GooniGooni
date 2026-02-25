"""
Modal Account management — SQLite-backed store.

Table: modal_accounts
  id           TEXT PRIMARY KEY
  label        TEXT           — human-readable name (e.g. "Account-1")
  token_id     TEXT           — Modal token ID  (MODAL_TOKEN_ID)
  token_secret TEXT           — Modal token secret (stored in plaintext; keep DB volume private)
  workspace    TEXT           — Modal workspace/org name (detected on deploy)
  status       TEXT           — pending | ready | failed | disabled
  added_at     TEXT           — ISO-8601
  last_used    TEXT           — ISO-8601 or NULL
  last_error   TEXT           — last failure message or NULL
  use_count    INTEGER        — successful dispatches

Status lifecycle:
  added → pending (deploy queued) → ready (deploy succeeded) ↔ in rotation
                                  → failed (deploy failed, manual retry)
                                  ↔ disabled (admin hides from rotation)
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from config import DB_PATH, RESULTS_PATH

# Accounts table lives in the same gallery.db
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
                use_count    INTEGER NOT NULL DEFAULT 0
            )
            """
        )


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def add_account(
    label: str,
    token_id: str,
    token_secret: str,
) -> str:
    """Insert a new account in 'pending' state. Returns account ID."""
    account_id = str(uuid.uuid4())
    now = _now_iso()
    with _lock, _db() as conn:
        conn.execute(
            """
            INSERT INTO modal_accounts
              (id, label, token_id, token_secret, status, added_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (account_id, label, token_id, token_secret, now),
        )
    return account_id


def get_account(account_id: str) -> Optional[dict]:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM modal_accounts WHERE id=?", (account_id,)
        ).fetchone()
    return dict(row) if row else None


def list_accounts() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM modal_accounts ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def list_ready_accounts() -> list[dict]:
    """Return only accounts eligible for rotation."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM modal_accounts WHERE status='ready' ORDER BY use_count ASC, last_used ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def update_account_status(
    account_id: str,
    status: str,
    workspace: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    fields = ["status = ?", "last_error = ?"]
    values: list = [status, error]
    if workspace is not None:
        fields.append("workspace = ?")
        values.append(workspace)
    values.append(account_id)

    with _lock, _db() as conn:
        conn.execute(
            f"UPDATE modal_accounts SET {', '.join(fields)} WHERE id=?",
            values,
        )


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
    """Re-enable a disabled account (sets it back to 'ready' if it was 'disabled')."""
    with _lock, _db() as conn:
        conn.execute(
            "UPDATE modal_accounts SET status='ready', last_error=NULL WHERE id=? AND status='disabled'",
            (account_id,),
        )
