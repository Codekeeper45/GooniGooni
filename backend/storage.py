"""
SQLite-backed storage layer for gallery metadata and task tracking.
The database lives inside the Modal 'results' Volume at /results/gallery.db.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
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
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

_CREATE_IDX_SQL = """
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_model    ON tasks(model);
CREATE INDEX IF NOT EXISTS idx_tasks_created  ON tasks(created_at DESC);
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
        conn.executescript(_CREATE_TASKS_SQL + _CREATE_IDX_SQL)


# ─── Task CRUD ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
) -> str:
    """Insert a new task row and return the generated task_id."""
    task_id = str(uuid.uuid4())
    now = _now_iso()
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO tasks
              (id, status, progress, model, type, mode, prompt, negative_prompt,
               parameters, width, height, seed, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                task_id, "pending", 0, model, gen_type, mode,
                prompt, negative_prompt,
                json.dumps(parameters),
                width, height, seed, now, now,
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
    values.append(task_id)
    with _db() as conn:
        conn.execute(
            f"UPDATE tasks SET {', '.join(fields)} WHERE id=?",
            values,
        )


def get_task(task_id: str) -> Optional[StatusResponse]:
    """Return a StatusResponse for a single task, or None if not found."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE id=?", (task_id,)
        ).fetchone()

    if row is None:
        return None

    base_url = os.environ.get("PUBLIC_BASE_URL", "")
    return StatusResponse(
        task_id=row["id"],
        status=TaskStatus(row["status"]),
        progress=row["progress"],
        result_url=f"{base_url}/results/{row['id']}" if row["result_path"] else None,
        preview_url=f"{base_url}/preview/{row['id']}" if row["preview_path"] else None,
        error=row["error_msg"],
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

    where_clauses = ["status = 'done'"]
    params: list[Any] = []

    if model_filter:
        where_clauses.append("model = ?")
        params.append(model_filter)

    if type_filter:
        where_clauses.append("type = ?")
        params.append(type_filter)

    where_sql = " AND ".join(where_clauses)
    base_url = os.environ.get("PUBLIC_BASE_URL", "")

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
            preview_url=f"{base_url}/preview/{row['id']}",
            result_url=f"{base_url}/results/{row['id']}",
        )
        for row in rows
        if row["result_path"]  # Skip rows without result files
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

        # Remove files from volume
        for path in (row["result_path"], row["preview_path"]):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass  # Best-effort cleanup

        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    return True


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
