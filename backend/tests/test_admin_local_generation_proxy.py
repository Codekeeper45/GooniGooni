"""
Tests for local VM generation proxy behavior in admin_local.py.
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    import config
    from cryptography.fernet import Fernet

    db_file = str(tmp_path / "test_admin_local_proxy.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "RESULTS_PATH", str(tmp_path))
    monkeypatch.setenv("ACCOUNTS_ENCRYPT_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("API_KEY", "shared-api")

    import accounts
    import storage

    monkeypatch.setattr(accounts, "DB_PATH", db_file)
    monkeypatch.setattr(accounts, "RESULTS_PATH", str(tmp_path))
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    monkeypatch.setattr(storage, "RESULTS_PATH", str(tmp_path))
    storage.init_db()
    accounts.init_accounts_table()
    yield


import accounts  # noqa: E402
import admin_local  # noqa: E402
from schemas import GenerateRequest, GenerationType, ModelId  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload or "")
        self.content = b""
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


def _make_ready_account(label: str, workspace: str) -> str:
    account_id = accounts.add_account(label, f"{label}_id", f"{label}_secret")
    accounts.update_account_status(account_id, "checking")
    accounts.update_account_status(account_id, "ready", workspace=workspace, error=None)
    return account_id


def _sample_generate_request() -> GenerateRequest:
    return GenerateRequest(
        model=ModelId.pony,
        type=GenerationType.image,
        mode="txt2img",
        prompt="test prompt",
    )


def test_generate_fallbacks_to_second_ready_account_on_429(monkeypatch):
    first_id = _make_ready_account("first", "workspace-a")
    second_id = _make_ready_account("second", "workspace-b")

    class FakeAsyncClient:
        post_calls = 0

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            FakeAsyncClient.post_calls += 1
            if "workspace-a" in url:
                return _FakeResponse(429, {"detail": "rate limit"})
            if "workspace-b" in url:
                return _FakeResponse(200, {"task_id": "remote-task-2"})
            return _FakeResponse(500, {"detail": "unexpected workspace"})

    monkeypatch.setattr(admin_local.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(admin_local.generate(_sample_generate_request(), _="session-token"))

    assert result.task_id == "workspace-b::remote-task-2"
    assert result.status.value == "pending"
    assert FakeAsyncClient.post_calls >= 2
    first_row = accounts.get_account(first_id)
    second_row = accounts.get_account(second_id)
    assert first_row is not None and first_row["status"] in {"failed", "disabled"}
    assert second_row is not None and second_row["status"] == "ready"


def test_generate_returns_503_without_local_default_fallback(monkeypatch):
    _make_ready_account("only", "workspace-only")

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            return _FakeResponse(503, {"detail": "upstream unavailable"}, text="upstream unavailable")

    monkeypatch.setattr(admin_local.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(admin_local.generate(_sample_generate_request(), _="session-token"))

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "no_ready_accounts"

    # No local task should be created as implicit fallback.
    with sqlite3.connect(admin_local.storage.DB_PATH) as conn:
        count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    assert count == 0


def test_status_rejects_non_composite_task_id():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(admin_local.get_status("plain-task-id", _="session-token"))

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "invalid_task_id"
