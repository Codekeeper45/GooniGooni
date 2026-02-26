"""
SQLite-backed storage layer for gallery metadata and task tracking.
The database lives inside the Modal 'results' Volume at /results/gallery.db.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from config import DB_PATH, RESULTS_PATH, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from schemas import GalleryItemResponse, StatusResponse, TaskStatus


# ─── Schema DDL ───────────────────────────────────────────────────────────────

_CREATE_TASKS_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'pending',
    progress    INTEGER NOT NULL DEFAULT 0,
    model       TEXT NOT NULL,
    type        TEXT NOT NULL,
    mode        TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    negative_prompt TEXT NOT NULL DEFAULT '',
    parameters  TEXT NOT NULL DEFAULT '{}',
    width       INTEGER NOT NULL DEFAULT 720,
    height      INTEGER NOT NULL DEFAULT 1280,
    seed        INTEGER NOT NULL DEFAULT -1,
    result_path TEXT,
    preview_path TEXT,
    error_msg   TEXT,
    stage       TEXT,
    stage_detail TEXT,
    lane_mode   TEXT,
    fallback_reason TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

_CREATE_IDX_SQL = """
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_model    ON tasks(model);
CREATE INDEX IF NOT EXISTS idx_tasks_created  ON tasks(created_at DESC);
"""

_CREATE_SESSIONS_SQL = """
CREATE TABLE IF NOT EXISTS generation_sessions (
    token         TEXT PRIMARY KEY,
    issued_at     TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',
    client_context TEXT
);

CREATE INDEX IF NOT EXISTS idx_generation_sessions_status
    ON generation_sessions(status);
CREATE INDEX IF NOT EXISTS idx_generation_sessions_expires
    ON generation_sessions(expires_at);

CREATE TABLE IF NOT EXISTS admin_sessions (
    token                TEXT PRIMARY KEY,
    issued_at            TEXT NOT NULL,
    last_activity_at     TEXT NOT NULL,
    idle_timeout_seconds INTEGER NOT NULL DEFAULT 43200,
    status               TEXT NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_admin_sessions_status
    ON admin_sessions(status);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_last_activity
    ON admin_sessions(last_activity_at);

CREATE TABLE IF NOT EXISTS degraded_queue (
    task_id      TEXT PRIMARY KEY,
    admitted_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_degraded_queue_admitted
    ON degraded_queue(admitted_at);

CREATE TABLE IF NOT EXISTS operational_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type   TEXT NOT NULL,
    task_id      TEXT,
    model        TEXT,
    lane_mode    TEXT,
    value        TEXT,
    reason       TEXT,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operational_events_created
    ON operational_events(created_at DESC);
"""


# ─── Connection helper ────────────────────────────────────────────────────────

@contextmanager
def _db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a configured SQLite connection."""
    # Ensure the directory exists (runs inside Modal container)
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables and indexes if they don't exist. Call on startup."""
    with _db() as conn:
        conn.executescript(_CREATE_TASKS_SQL + _CREATE_IDX_SQL + _CREATE_SESSIONS_SQL)
        for ddl in (
            "ALTER TABLE tasks ADD COLUMN stage TEXT",
            "ALTER TABLE tasks ADD COLUMN stage_detail TEXT",
            "ALTER TABLE tasks ADD COLUMN lane_mode TEXT",
            "ALTER TABLE tasks ADD COLUMN fallback_reason TEXT",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                # Column already exists on upgraded databases.
                pass


def _public_base_url() -> Optional[str]:
    """
    Return configured absolute base URL without trailing slash.
    If not configured, return None so callers avoid emitting relative URLs.
    """
    raw = (os.environ.get("PUBLIC_BASE_URL") or "").strip()
    if not raw:
        return None
    return raw.rstrip("/")


# ─── Task CRUD ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_token() -> str:
    return secrets.token_urlsafe(48)


def create_generation_session(
    ttl_seconds: int = 24 * 3600,
    client_context: Optional[str] = None,
) -> tuple[str, datetime]:
    token = _new_token()
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO generation_sessions(token, issued_at, expires_at, status, client_context)
            VALUES (?, ?, ?, 'active', ?)
            """,
            (token, issued_at.isoformat(), expires_at.isoformat(), client_context),
        )
    return token, expires_at


def validate_generation_session(token: str) -> tuple[bool, Optional[str], Optional[datetime]]:
    with _db() as conn:
        row = conn.execute(
            """
            SELECT token, expires_at, status
            FROM generation_sessions
            WHERE token=?
            """,
            (token,),
        ).fetchone()
        if row is None:
            return False, "missing", None

        status = row["status"]
        expires_at = datetime.fromisoformat(row["expires_at"])
        now = datetime.now(timezone.utc)

        if status == "revoked":
            return False, "revoked", expires_at
        if status != "active":
            return False, "expired", expires_at
        if now >= expires_at:
            conn.execute(
                "UPDATE generation_sessions SET status='expired' WHERE token=?",
                (token,),
            )
            return False, "expired", expires_at

    return True, None, expires_at


def revoke_generation_session(token: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE generation_sessions SET status='revoked' WHERE token=?",
            (token,),
        )


# Backward-compatible aliases used by legacy contracts/tests.
def create_session(
    ttl_seconds: int = 24 * 3600,
    client_context: Optional[str] = None,
) -> tuple[str, datetime]:
    return create_generation_session(ttl_seconds=ttl_seconds, client_context=client_context)


def get_session(token: str) -> Optional[dict[str, Any]]:
    with _db() as conn:
        row = conn.execute(
            """
            SELECT token, issued_at, expires_at, status, client_context
            FROM generation_sessions
            WHERE token=?
            """,
            (token,),
        ).fetchone()
    return dict(row) if row else None


def revoke_session(token: str) -> None:
    revoke_generation_session(token)


def create_admin_session(idle_timeout_seconds: int = 12 * 3600) -> tuple[str, datetime]:
    token = _new_token()
    now = datetime.now(timezone.utc)
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO admin_sessions(token, issued_at, last_activity_at, idle_timeout_seconds, status)
            VALUES (?, ?, ?, ?, 'active')
            """,
            (token, now.isoformat(), now.isoformat(), idle_timeout_seconds),
        )
    return token, now


def validate_admin_session(
    token: str,
    *,
    touch: bool = False,
) -> tuple[bool, Optional[str], Optional[datetime]]:
    with _db() as conn:
        row = conn.execute(
            """
            SELECT token, status, last_activity_at, idle_timeout_seconds
            FROM admin_sessions
            WHERE token=?
            """,
            (token,),
        ).fetchone()
        if row is None:
            return False, "missing", None

        status = row["status"]
        last_activity = datetime.fromisoformat(row["last_activity_at"])
        idle_timeout = int(row["idle_timeout_seconds"])
        expires_at = last_activity + timedelta(seconds=idle_timeout)
        now = datetime.now(timezone.utc)

        if status == "revoked":
            return False, "revoked", expires_at
        if status != "active":
            return False, "expired", expires_at
        if now >= expires_at:
            conn.execute(
                "UPDATE admin_sessions SET status='expired' WHERE token=?",
                (token,),
            )
            return False, "expired", expires_at

        if touch:
            conn.execute(
                "UPDATE admin_sessions SET last_activity_at=? WHERE token=?",
                (now.isoformat(), token),
            )
            expires_at = now + timedelta(seconds=idle_timeout)

    return True, None, expires_at


def get_admin_session(token: str) -> Optional[dict[str, Any]]:
    with _db() as conn:
        row = conn.execute(
            """
            SELECT token, issued_at, last_activity_at, idle_timeout_seconds, status
            FROM admin_sessions
            WHERE token=?
            """,
            (token,),
        ).fetchone()
    return dict(row) if row else None


def revoke_admin_session(token: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE admin_sessions SET status='revoked' WHERE token=?",
            (token,),
        )


def create_task(
    model: str,
    gen_type: str,
    mode: str,
    prompt: str,
    negative_prompt: str,
    parameters: dict[str, Any],
    width: int,
    height: int,
    seed: int,
    lane_mode: Optional[str] = None,
    fallback_reason: Optional[str] = None,
) -> str:
    """Insert a new task row and return the generated task_id."""
    task_id = str(uuid.uuid4())
    now = _now_iso()
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO tasks
              (id, status, progress, model, type, mode, prompt, negative_prompt,
               parameters, width, height, seed, lane_mode, fallback_reason, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                task_id, "pending", 0, model, gen_type, mode,
                prompt, negative_prompt,
                json.dumps(parameters),
                width, height, seed, lane_mode, fallback_reason, now, now,
            ),
        )
    return task_id


def update_task_status(
    task_id: str,
    status: str,
    progress: int = 0,
    result_path: Optional[str] = None,
    preview_path: Optional[str] = None,
    error_msg: Optional[str] = None,
    stage: Optional[str] = None,
    stage_detail: Optional[str] = None,
    lane_mode: Optional[str] = None,
    fallback_reason: Optional[str] = None,
) -> None:
    """Update task status, progress, and optional result/preview paths.
    Only non-None optional fields are written — avoids overwriting
    previously saved paths during intermediate progress updates.
    """
    now = _now_iso()
    fields = ["status=?", "progress=?", "updated_at=?"]
    values: list[Any] = [status, progress, now]
    if result_path is not None:
        fields.append("result_path=?")
        values.append(result_path)
    if preview_path is not None:
        fields.append("preview_path=?")
        values.append(preview_path)
    if error_msg is not None:
        fields.append("error_msg=?")
        values.append(error_msg)
    if stage is not None:
        fields.append("stage=?")
        values.append(stage)
    if stage_detail is not None:
        fields.append("stage_detail=?")
        values.append(stage_detail)
    if lane_mode is not None:
        fields.append("lane_mode=?")
        values.append(lane_mode)
    if fallback_reason is not None:
        fields.append("fallback_reason=?")
        values.append(fallback_reason)
    values.append(task_id)
    with _db() as conn:
        conn.execute(
            f"UPDATE tasks SET {', '.join(fields)} WHERE id=?",
            values,
        )


def get_task(task_id: str) -> Optional[StatusResponse]:
    """Return a StatusResponse for a single task, or None if not found."""
    with _db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        diag_rows = conn.execute(
            """
            SELECT event_type, value, reason, created_at
            FROM operational_events
            WHERE task_id=?
            ORDER BY id DESC
            LIMIT 20
            """,
            (task_id,),
        ).fetchall()

    if row is None:
        return None

    base_url = _public_base_url()
    diagnostics = {
        "events": [
            {
                "event_type": event["event_type"],
                "value": event["value"],
                "reason": event["reason"],
                "created_at": event["created_at"],
            }
            for event in diag_rows
        ]
    } if diag_rows else None
    return StatusResponse(
        task_id=row["id"],
        status=TaskStatus(row["status"]),
        progress=row["progress"],
        stage=row["stage"],
        stage_detail=row["stage_detail"],
        lane_mode=row["lane_mode"],
        fallback_reason=row["fallback_reason"],
        diagnostics=diagnostics,
        result_url=f"{base_url}/results/{row['id']}" if row["result_path"] and base_url else None,
        preview_url=f"{base_url}/preview/{row['id']}" if row["preview_path"] and base_url else None,
        error_msg=row["error_msg"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


# ─── Gallery CRUD ─────────────────────────────────────────────────────────────

def list_gallery(
    page: int = 1,
    per_page: int = DEFAULT_PAGE_SIZE,
    sort: str = "created_at",
    model_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
) -> tuple[list[GalleryItemResponse], int]:
    """
    Return a paginated list of completed gallery items and the total count.
    Only rows with status='done' are included.
    """
    per_page = min(per_page, MAX_PAGE_SIZE)
    offset = (page - 1) * per_page

    # Whitelist sort columns to prevent SQL injection
    allowed_sorts = {"created_at", "model", "width", "height"}
    if sort not in allowed_sorts:
        sort = "created_at"

    where_clauses = ["status = 'done'", "result_path IS NOT NULL"]
    params: list[Any] = []

    if model_filter:
        where_clauses.append("model = ?")
        params.append(model_filter)

    if type_filter:
        where_clauses.append("type = ?")
        params.append(type_filter)

    where_sql = " AND ".join(where_clauses)
    base_url = _public_base_url()

    with _db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM tasks WHERE {where_sql}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""
            SELECT * FROM tasks WHERE {where_sql}
            ORDER BY {sort} DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

    items = [
        GalleryItemResponse(
            id=row["id"],
            model=row["model"],
            type=row["type"],
            mode=row["mode"],
            prompt=row["prompt"],
            negative_prompt=row["negative_prompt"],
            parameters=json.loads(row["parameters"] or "{}"),
            width=row["width"],
            height=row["height"],
            seed=row["seed"],
            created_at=datetime.fromisoformat(row["created_at"]),
            preview_url=f"{base_url}/preview/{row['id']}" if base_url else None,
            result_url=f"{base_url}/results/{row['id']}" if base_url else None,
        )
        for row in rows
    ]

    return items, total


def delete_gallery_item(task_id: str) -> bool:
    """
    Delete the task row and its files from the results volume.
    Returns True if a row was deleted, False if not found.
    """
    with _db() as conn:
        row = conn.execute(
            "SELECT result_path, preview_path FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
        if row is None:
            return False
        result_path = row["result_path"]
        preview_path = row["preview_path"]
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    # Best-effort file cleanup after DB transaction has committed.
    for path in (result_path, preview_path):
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    return True


def mark_stale_tasks_failed(max_age_hours: int = 2) -> int:
    """
    Mark stuck pending/processing tasks as failed.
    Returns number of rows updated.
    """
    cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
    updated = 0
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id, updated_at
            FROM tasks
            WHERE status IN ('pending', 'processing')
            """
        ).fetchall()
        for row in rows:
            try:
                updated_ts = datetime.fromisoformat(row["updated_at"]).timestamp()
            except Exception:
                continue
            if updated_ts < cutoff:
                conn.execute(
                    """
                    UPDATE tasks
                    SET status='failed', error_msg=?, updated_at=?
                    WHERE id=?
                    """,
                    ("Task expired due to timeout", _now_iso(), row["id"]),
                )
                updated += 1
    return updated


def list_tasks(status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    with _db() as conn:
        if status:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def delete_task(task_id: str) -> bool:
    return delete_gallery_item(task_id)


def degraded_queue_size() -> int:
    with _db() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM degraded_queue").fetchone()[0])


def try_admit_degraded_task(task_id: str, max_depth: int) -> tuple[bool, int]:
    """
    Try to reserve one degraded-mode queue slot for a task.
    Returns (admitted, current_depth_after_attempt).
    """
    now = _now_iso()
    with _db() as conn:
        current = int(conn.execute("SELECT COUNT(*) FROM degraded_queue").fetchone()[0])
        if current >= max_depth:
            return False, current
        conn.execute(
            "INSERT OR REPLACE INTO degraded_queue(task_id, admitted_at) VALUES (?, ?)",
            (task_id, now),
        )
        depth = int(conn.execute("SELECT COUNT(*) FROM degraded_queue").fetchone()[0])
        return True, depth


def release_degraded_task(task_id: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM degraded_queue WHERE task_id=?", (task_id,))


def record_operational_event(
    event_type: str,
    *,
    task_id: Optional[str] = None,
    model: Optional[str] = None,
    lane_mode: Optional[str] = None,
    value: Optional[Any] = None,
    reason: Optional[str] = None,
) -> None:
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO operational_events(event_type, task_id, model, lane_mode, value, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type,
                task_id,
                model,
                lane_mode,
                None if value is None else str(value),
                reason,
                _now_iso(),
            ),
        )


def list_operational_events(limit: int = 100) -> list[dict[str, Any]]:
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id, event_type, task_id, model, lane_mode, value, reason, created_at
            FROM operational_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_operational_snapshot() -> dict[str, Any]:
    with _db() as conn:
        queue_depth = int(conn.execute("SELECT COUNT(*) FROM degraded_queue").fetchone()[0])
        overload_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM operational_events WHERE event_type='queue_overloaded'"
            ).fetchone()[0]
        )
        timeout_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM operational_events WHERE event_type='queue_timeout'"
            ).fetchone()[0]
        )
        fallback_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM operational_events WHERE event_type='fallback_activated'"
            ).fetchone()[0]
        )
    return {
        "queue_depth": queue_depth,
        "queue_overloaded_count": overload_count,
        "queue_timeout_count": timeout_count,
        "fallback_count": fallback_count,
    }



# ─── Raw data access (used by file-serving and admin endpoints) ───────────────

def get_raw_task(task_id: str) -> dict | None:
    """Return raw task dict for file-serving endpoints."""
    with _db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None


def get_audit_logs(limit: int = 100) -> list[dict]:
    """Return recent admin audit log entries, newest first."""
    if not os.path.exists(DB_PATH):
        return []
    with _db() as conn:
        try:
            rows = conn.execute(
                "SELECT * FROM admin_audit_log ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            # Table may not exist yet if admin_security hasn't initialized
            return []


def check_storage_health() -> bool:
    """Return True when SQLite is reachable through the standard DB context."""
    try:
        with _db() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


# ─── File path helpers ────────────────────────────────────────────────────────

def task_dir(task_id: str) -> Path:
    """Return the directory for a task's files (creates it if needed)."""
    d = Path(RESULTS_PATH) / task_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def result_file_path(task_id: str, extension: str) -> str:
    """Return the absolute path for the main result file."""
    return str(task_dir(task_id) / f"result.{extension}")


def preview_file_path(task_id: str) -> str:
    """Return the absolute path for the preview JPEG thumbnail."""
    return str(task_dir(task_id) / "preview.jpg")
