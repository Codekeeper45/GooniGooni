"""
Unit tests for backend/accounts.py
Uses a temporary SQLite database — no Modal, no GPU.
"""
import sys
from pathlib import Path

import pytest

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    import config
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "RESULTS_PATH", str(tmp_path))

    import accounts
    monkeypatch.setattr(accounts, "DB_PATH", db_file)
    monkeypatch.setattr(accounts, "RESULTS_PATH", str(tmp_path))
    accounts.init_accounts_table()
    yield


import accounts  # noqa: E402


class TestAddAccount:
    def test_returns_uuid(self):
        aid = accounts.add_account("Test", "tok_id", "tok_sec")
        assert len(aid) == 36

    def test_initial_status_is_pending(self):
        aid = accounts.add_account("Test", "tok_id", "tok_sec")
        row = accounts.get_account(aid)
        assert row["status"] == "pending"

    def test_stores_label_and_credentials(self):
        aid = accounts.add_account("MyAccount", "id123", "sec456")
        row = accounts.get_account(aid)
        assert row["label"] == "MyAccount"
        assert row["token_id"] == "id123"
        assert row["token_secret"] == "sec456"

    def test_use_count_starts_at_zero(self):
        aid = accounts.add_account("Test", "t", "s")
        row = accounts.get_account(aid)
        assert row["use_count"] == 0


class TestUpdateStatus:
    def _add(self):
        return accounts.add_account("Test", "t", "s")

    def test_update_to_ready(self):
        aid = self._add()
        accounts.update_account_status(aid, "ready", workspace="my-workspace")
        row = accounts.get_account(aid)
        assert row["status"] == "ready"
        assert row["workspace"] == "my-workspace"

    def test_update_to_failed_with_error(self):
        aid = self._add()
        accounts.update_account_status(aid, "failed", error="deploy crashed")
        row = accounts.get_account(aid)
        assert row["status"] == "failed"
        assert row["last_error"] == "deploy crashed"

    def test_update_clears_error_on_success(self):
        aid = self._add()
        accounts.update_account_status(aid, "failed", error="boom")
        accounts.update_account_status(aid, "ready", error=None)
        row = accounts.get_account(aid)
        assert row["last_error"] is None


class TestMarkUsed:
    def test_increments_use_count(self):
        aid = accounts.add_account("Test", "t", "s")
        accounts.update_account_status(aid, "ready")
        accounts.mark_account_used(aid)
        accounts.mark_account_used(aid)
        row = accounts.get_account(aid)
        assert row["use_count"] == 2

    def test_sets_last_used(self):
        aid = accounts.add_account("Test", "t", "s")
        accounts.mark_account_used(aid)
        row = accounts.get_account(aid)
        assert row["last_used"] is not None


class TestListReadyAccounts:
    def test_excludes_pending(self):
        accounts.add_account("Pending", "t", "s")  # stays pending
        assert accounts.list_ready_accounts() == []

    def test_includes_ready(self):
        aid = accounts.add_account("Ready", "t", "s")
        accounts.update_account_status(aid, "ready")
        rows = accounts.list_ready_accounts()
        assert len(rows) == 1
        assert rows[0]["id"] == aid

    def test_sorted_by_use_count(self):
        a1 = accounts.add_account("A1", "t", "s")
        a2 = accounts.add_account("A2", "t", "s")
        accounts.update_account_status(a1, "ready")
        accounts.update_account_status(a2, "ready")
        # Make a1 more used
        accounts.mark_account_used(a1)
        accounts.mark_account_used(a1)
        rows = accounts.list_ready_accounts()
        # a2 should come first (use_count=0)
        assert rows[0]["id"] == a2

    def test_excludes_disabled(self):
        aid = accounts.add_account("D", "t", "s")
        accounts.update_account_status(aid, "ready")
        accounts.disable_account(aid)
        assert accounts.list_ready_accounts() == []


class TestDeleteAccount:
    def test_deletes_existing(self):
        aid = accounts.add_account("Del", "t", "s")
        assert accounts.delete_account(aid) is True
        assert accounts.get_account(aid) is None

    def test_delete_nonexistent_returns_false(self):
        assert accounts.delete_account("nonexistent") is False


class TestDisableEnable:
    def test_disable_removes_from_rotation(self):
        aid = accounts.add_account("DA", "t", "s")
        accounts.update_account_status(aid, "ready")
        accounts.disable_account(aid)
        row = accounts.get_account(aid)
        assert row["status"] == "disabled"

    def test_enable_restores_to_ready(self):
        aid = accounts.add_account("EA", "t", "s")
        accounts.update_account_status(aid, "ready")
        accounts.disable_account(aid)
        accounts.enable_account(aid)
        row = accounts.get_account(aid)
        assert row["status"] == "ready"
