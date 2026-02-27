"""
Tests for admin account onboarding preflight checks.
"""
from __future__ import annotations

import asyncio
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

    db_file = str(tmp_path / "test_admin_add.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "RESULTS_PATH", str(tmp_path))
    monkeypatch.setenv("ACCOUNTS_ENCRYPT_KEY", Fernet.generate_key().decode())

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


def _set_shared_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "shared_api")
    monkeypatch.setenv("ADMIN_LOGIN", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "pbkdf2_sha256$600000$salt$hash")
    monkeypatch.setenv("HF_TOKEN", "hf_test_value")


def test_admin_add_account_fails_fast_when_shared_env_missing(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("ADMIN_LOGIN", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            admin_local.admin_add_account(
                label="Account-1",
                token_id="tok_id",
                token_secret="tok_secret",
                _ip="127.0.0.1",
            )
        )

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "admin_env_missing"
    assert len(accounts.list_accounts()) == 0


def test_admin_add_account_creates_row_and_starts_deploy(monkeypatch):
    _set_shared_env(monkeypatch)
    called = {"account_id": None}

    def fake_deploy_async(account_id: str):
        called["account_id"] = account_id
        return None

    monkeypatch.setattr(admin_local, "deploy_account_async", fake_deploy_async)

    result = asyncio.run(
        admin_local.admin_add_account(
            label="Account-2",
            token_id="tok_id_2",
            token_secret="tok_secret_2",
            _ip="127.0.0.1",
        )
    )

    assert result["status"] == "pending"
    assert called["account_id"] == result["id"]
    row = accounts.get_account(result["id"])
    assert row is not None
    assert row["label"] == "Account-2"
