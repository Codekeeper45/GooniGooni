"""
Unit tests for backend/accounts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    import config
    from cryptography.fernet import Fernet

    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "RESULTS_PATH", str(tmp_path))
    monkeypatch.setenv("ACCOUNTS_ENCRYPT_KEY", Fernet.generate_key().decode())

    import accounts

    monkeypatch.setattr(accounts, "DB_PATH", db_file)
    monkeypatch.setattr(accounts, "RESULTS_PATH", str(tmp_path))
    accounts.init_accounts_table()
    yield


import accounts  # noqa: E402


def test_add_account_initial_status_pending():
    account_id = accounts.add_account("Test", "tok_id", "tok_secret")
    row = accounts.get_account(account_id)
    assert row is not None
    assert row["status"] == "pending"


def test_allowed_fsm_pending_to_checking_to_ready():
    account_id = accounts.add_account("Test", "tok_id", "tok_secret")
    accounts.update_account_status(account_id, "checking")
    accounts.update_account_status(account_id, "ready", workspace="ws-test")
    row = accounts.get_account(account_id)
    assert row["status"] == "ready"
    assert row["workspace"] == "ws-test"


def test_forbidden_ready_to_pending_transition():
    account_id = accounts.add_account("Test", "tok_id", "tok_secret")
    accounts.update_account_status(account_id, "checking")
    accounts.update_account_status(account_id, "ready")

    with pytest.raises(ValueError):
        accounts.update_account_status(account_id, "pending")


def test_forbidden_failed_to_ready_without_checking():
    account_id = accounts.add_account("Test", "tok_id", "tok_secret")
    accounts.update_account_status(account_id, "failed", error="health failed")

    with pytest.raises(ValueError):
        accounts.update_account_status(account_id, "ready")


def test_failed_can_recover_via_checking_then_ready():
    account_id = accounts.add_account("Test", "tok_id", "tok_secret")
    accounts.update_account_status(account_id, "failed", error="health failed")
    accounts.update_account_status(account_id, "checking")
    accounts.update_account_status(account_id, "ready", error=None)

    row = accounts.get_account(account_id)
    assert row["status"] == "ready"


def test_list_ready_accounts_excludes_non_ready():
    pending_id = accounts.add_account("Pending", "tok_id", "tok_secret")
    checking_id = accounts.add_account("Checking", "tok_id", "tok_secret")
    ready_id = accounts.add_account("Ready", "tok_id", "tok_secret")

    accounts.update_account_status(checking_id, "checking")
    accounts.update_account_status(ready_id, "checking")
    accounts.update_account_status(ready_id, "ready")

    ids = [row["id"] for row in accounts.list_ready_accounts()]
    assert ready_id in ids
    assert pending_id not in ids
    assert checking_id not in ids


def test_disable_enable_cycle():
    account_id = accounts.add_account("Test", "tok_id", "tok_secret")
    accounts.update_account_status(account_id, "checking")
    accounts.update_account_status(account_id, "ready")

    accounts.disable_account(account_id)
    row = accounts.get_account(account_id)
    assert row["status"] == "disabled"

    accounts.enable_account(account_id)
    row = accounts.get_account(account_id)
    assert row["status"] == "ready"


def test_status_transition_logging(caplog):
    caplog.set_level("INFO", logger="accounts")
    account_id = accounts.add_account("LogTest", "tok_id", "tok_secret")
    accounts.update_account_status(account_id, "checking")
    accounts.update_account_status(account_id, "ready")

    messages = [rec.getMessage() for rec in caplog.records if rec.name == "accounts"]
    assert any("prev=pending new=checking" in msg for msg in messages)
    assert any("prev=checking new=ready" in msg for msg in messages)
