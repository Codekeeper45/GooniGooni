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


def test_allowed_fsm_with_deploying_stage():
    account_id = accounts.add_account("DeployFlow", "tok_id", "tok_secret")
    accounts.update_account_status(account_id, "checking")
    accounts.update_account_status(account_id, "deploying")
    accounts.update_account_status(account_id, "checking")
    accounts.update_account_status(account_id, "ready", workspace="ws-deploy")
    row = accounts.get_account(account_id)
    assert row is not None
    assert row["status"] == "ready"
    assert row["workspace"] == "ws-deploy"


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
    deploying_id = accounts.add_account("Deploying", "tok_id", "tok_secret")
    ready_id = accounts.add_account("Ready", "tok_id", "tok_secret")

    accounts.update_account_status(checking_id, "checking")
    accounts.update_account_status(deploying_id, "checking")
    accounts.update_account_status(deploying_id, "deploying")
    accounts.update_account_status(ready_id, "checking")
    accounts.update_account_status(ready_id, "ready")

    ids = [row["id"] for row in accounts.list_ready_accounts()]
    assert ready_id in ids
    assert pending_id not in ids
    assert checking_id not in ids
    assert deploying_id not in ids


def test_list_ready_accounts_orders_by_last_used_then_use_count():
    never_used = accounts.add_account("NeverUsed", "tok_id", "tok_secret")
    old_used = accounts.add_account("OldUsed", "tok_id", "tok_secret")
    recent_used = accounts.add_account("RecentUsed", "tok_id", "tok_secret")

    for aid in (never_used, old_used, recent_used):
        accounts.update_account_status(aid, "checking")
        accounts.update_account_status(aid, "ready")

    with accounts._db() as conn:  # test-only setup
        conn.execute(
            "UPDATE modal_accounts SET use_count=?, last_used=? WHERE id=?",
            (5, None, never_used),
        )
        conn.execute(
            "UPDATE modal_accounts SET use_count=?, last_used=? WHERE id=?",
            (10, "2026-01-01T00:00:00+00:00", old_used),
        )
        conn.execute(
            "UPDATE modal_accounts SET use_count=?, last_used=? WHERE id=?",
            (0, "2026-01-02T00:00:00+00:00", recent_used),
        )

    ids = [row["id"] for row in accounts.list_ready_accounts()]
    assert ids[:3] == [never_used, old_used, recent_used]


def test_list_ready_accounts_tiebreaks_by_use_count():
    low_count = accounts.add_account("Low", "tok_id", "tok_secret")
    high_count = accounts.add_account("High", "tok_id", "tok_secret")
    same_last_used = "2026-01-01T00:00:00+00:00"

    for aid in (low_count, high_count):
        accounts.update_account_status(aid, "checking")
        accounts.update_account_status(aid, "ready")

    with accounts._db() as conn:  # test-only setup
        conn.execute(
            "UPDATE modal_accounts SET use_count=?, last_used=? WHERE id=?",
            (1, same_last_used, low_count),
        )
        conn.execute(
            "UPDATE modal_accounts SET use_count=?, last_used=? WHERE id=?",
            (9, same_last_used, high_count),
        )

    ids = [row["id"] for row in accounts.list_ready_accounts()]
    assert ids[:2] == [low_count, high_count]


def test_pick_and_mark_ready_account_updates_usage_immediately():
    account_id = accounts.add_account("PickMe", "tok_id", "tok_secret")
    accounts.update_account_status(account_id, "checking")
    accounts.update_account_status(account_id, "ready")

    row_before = accounts.get_account(account_id)
    assert row_before["use_count"] == 0
    assert row_before["last_used"] is None

    picked = accounts.pick_and_mark_ready_account()
    assert picked is not None
    assert picked["id"] == account_id

    row_after = accounts.get_account(account_id)
    assert row_after["use_count"] == 1
    assert row_after["last_used"] is not None


def test_pick_and_mark_ready_account_respects_exclude_ids():
    a = accounts.add_account("A", "tok_a", "sec_a")
    b = accounts.add_account("B", "tok_b", "sec_b")
    for aid in (a, b):
        accounts.update_account_status(aid, "checking")
        accounts.update_account_status(aid, "ready")

    picked = accounts.pick_and_mark_ready_account(exclude_ids=[a])
    assert picked is not None
    assert picked["id"] == b


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


def test_mark_account_failed_increments_counter_and_sets_failed_at():
    account_id = accounts.add_account("Test", "tok_id", "tok_secret")
    accounts.mark_account_failed(account_id, "timeout", max_fail_count=6)
    row = accounts.get_account(account_id)
    assert row["status"] == "failed"
    assert row["fail_count"] == 1
    assert row["failed_at"] is not None


def test_mark_account_failed_disables_after_threshold():
    account_id = accounts.add_account("Test", "tok_id", "tok_secret")
    accounts.mark_account_failed(account_id, "oom", max_fail_count=1)
    row = accounts.get_account(account_id)
    assert row["status"] == "disabled"
    assert row["fail_count"] == 1


def test_mark_account_failed_config_error_disables_immediately():
    account_id = accounts.add_account("Cfg", "tok_id", "tok_secret")
    accounts.mark_account_failed(account_id, "Secret sync failed for huggingface")
    row = accounts.get_account(account_id)
    assert row["status"] == "disabled"
    assert row["failure_type"] == "config_failed"


def test_recover_failed_accounts_after_cooldown():
    account_id = accounts.add_account("Test", "tok_id", "tok_secret")
    accounts.mark_account_failed(account_id, "transient", max_fail_count=6)
    recovered = accounts.recover_failed_accounts(cooldown_seconds=0)
    assert recovered == 0

    # Force old failed_at and recover.
    with accounts._db() as conn:  # test-only direct setup
        conn.execute(
            "UPDATE modal_accounts SET failed_at=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", account_id),
        )
    recovered = accounts.recover_failed_accounts(cooldown_seconds=60)
    assert recovered == 1
    row = accounts.get_account(account_id)
    assert row["status"] == "ready"
    assert row["failed_at"] is None


def test_recover_failed_accounts_skips_config_failures():
    account_id = accounts.add_account("CfgRecover", "tok_id", "tok_secret")
    with accounts._db() as conn:  # test-only setup
        conn.execute(
            """
            UPDATE modal_accounts
            SET status='failed', failure_type='config_failed', failed_at=?
            WHERE id=?
            """,
            ("2000-01-01T00:00:00+00:00", account_id),
        )
    recovered = accounts.recover_failed_accounts(cooldown_seconds=60)
    assert recovered == 0
    row = accounts.get_account(account_id)
    assert row["status"] == "failed"
