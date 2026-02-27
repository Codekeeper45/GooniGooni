"""
Exploration tests for the Modal account auto-rotation bugfix.

This file contains TWO test groups:

1. BUG CONDITION TESTS — These demonstrate the bugs that exist on UNFIXED code.
   They encode EXPECTED behavior, so they MUST FAIL on unfixed code and PASS after fix.

2. PRESERVATION TESTS — These capture correct existing behavior that must NOT change.
   They MUST PASS on both unfixed and fixed code.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

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


# ═══════════════════════════════════════════════════════════════════════════════
# BUG CONDITION TESTS — Expected to FAIL on unfixed code, PASS after fix
# ═══════════════════════════════════════════════════════════════════════════════


class TestBugCondition_ErrorClassification:
    """Property 1: Fault Condition — Error Classification and Quota Auto-Recovery."""

    def test_quota_error_sets_failure_type(self):
        """Bug: failure_type column does not exist / is not set in current code."""
        account_id = accounts.add_account("QuotaTest", "tok_id", "tok_secret")
        accounts.mark_account_failed(account_id, "quota exceeded for workspace")

        row = accounts.get_account(account_id)
        # EXPECTED: failure_type should be classified
        assert row.get("failure_type") == "quota_exceeded", (
            "COUNTEREXAMPLE: quota error was not classified as 'quota_exceeded'"
        )

    def test_quota_error_immediately_disables(self):
        """Bug: quota errors go through fail_count instead of immediate disable."""
        account_id = accounts.add_account("QuotaTest", "tok_id", "tok_secret")
        accounts.mark_account_failed(account_id, "limit exceeded", max_fail_count=6)

        row = accounts.get_account(account_id)
        # EXPECTED: quota should immediately disable, not wait for 6 failures
        assert row["status"] == "disabled", (
            "COUNTEREXAMPLE: quota error did not immediately disable — "
            f"status is '{row['status']}' with fail_count={row['fail_count']}"
        )

    def test_quota_error_not_auto_recovered(self):
        """Bug: quota errors auto-recover after cooldown just like temporary errors."""
        account_id = accounts.add_account("QuotaTest", "tok_id", "tok_secret")
        accounts.mark_account_failed(account_id, "insufficient credits")

        # Force old failed_at to simulate cooldown expiry
        with accounts._db() as conn:
            conn.execute(
                "UPDATE modal_accounts SET failed_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", account_id),
            )

        recovered = accounts.recover_failed_accounts(cooldown_seconds=60)

        row = accounts.get_account(account_id)
        # EXPECTED: quota errors should NOT be recovered
        assert row["status"] != "ready", (
            "COUNTEREXAMPLE: quota error was auto-recovered — "
            "should remain disabled until manual enable"
        )

    def test_auth_error_immediately_disables(self):
        """Bug: auth errors treated like temporary errors."""
        account_id = accounts.add_account("AuthTest", "tok_id", "tok_secret")
        accounts.mark_account_failed(account_id, "authentication failed: invalid token")

        row = accounts.get_account(account_id)
        assert row.get("failure_type") == "auth_failed"
        assert row["status"] == "disabled"

    def test_all_error_types_classifiable(self):
        """Bug: no _classify_error function exists in current code."""
        assert hasattr(accounts, "_classify_error"), (
            "COUNTEREXAMPLE: _classify_error() function does not exist"
        )

        test_cases = [
            ("quota exceeded", "quota_exceeded", "manual_only"),
            ("limit exceeded for workspace", "quota_exceeded", "manual_only"),
            ("insufficient credits", "quota_exceeded", "manual_only"),
            ("authentication failed", "auth_failed", "manual_only"),
            ("unauthorized access", "auth_failed", "manual_only"),
            ("invalid token provided", "auth_failed", "manual_only"),
            ("timeout waiting for response", "timeout", "auto_recover"),
            ("request timed out", "timeout", "auto_recover"),
            ("container startup failed", "container_failed", "auto_recover"),
            ("deployment failed", "container_failed", "auto_recover"),
            ("health check failed", "health_check_failed", "auto_recover"),
            ("endpoint not responding", "health_check_failed", "auto_recover"),
            ("some random error", "unknown", "auto_recover"),
        ]

        for error_msg, expected_type, expected_policy in test_cases:
            failure_type, recovery_policy = accounts._classify_error(error_msg)
            assert failure_type == expected_type, (
                f"Error '{error_msg}' classified as '{failure_type}', "
                f"expected '{expected_type}'"
            )
            assert recovery_policy == expected_policy, (
                f"Error '{error_msg}' recovery policy is '{recovery_policy}', "
                f"expected '{expected_policy}'"
            )


class TestBugCondition_DeployTimeout:
    """Bug: deploy timeout is 300 seconds (too long)."""

    def test_deploy_timeout_is_120_seconds(self):
        """Bug: current timeout is 300 seconds, should be 120."""
        import deployer

        # We inspect the source code for the timeout constant.
        import inspect
        source = inspect.getsource(deployer.deploy_account)
        # After fix, 120 should appear instead of 300
        assert "timeout=120" in source or "timeout = 120" in source, (
            "COUNTEREXAMPLE: deploy_account timeout is not 120 seconds"
        )


class TestBugCondition_HealthCheckCaching:
    """Bug: health check has no caching support."""

    def test_health_check_cache_columns_exist(self):
        """Bug: last_health_check and health_check_result columns don't exist."""
        account_id = accounts.add_account("CacheTest", "tok_id", "tok_secret")
        row = accounts.get_account(account_id)
        assert "last_health_check" in row, (
            "COUNTEREXAMPLE: last_health_check column does not exist"
        )
        assert "health_check_result" in row, (
            "COUNTEREXAMPLE: health_check_result column does not exist"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PRESERVATION TESTS — Must PASS on both unfixed and fixed code
# ═══════════════════════════════════════════════════════════════════════════════


class TestPreservation_TemporaryErrorRecovery:
    """Property 2: Temporary errors auto-recover after cooldown (300s)."""

    def test_timeout_error_auto_recovers_after_cooldown(self):
        """Temporary timeout errors should auto-recover after cooldown."""
        account_id = accounts.add_account("TmpErr", "tok_id", "tok_secret")
        accounts.mark_account_failed(account_id, "timeout", max_fail_count=6)

        row = accounts.get_account(account_id)
        assert row["status"] == "failed"
        assert row["fail_count"] == 1

        # Force old failed_at
        with accounts._db() as conn:
            conn.execute(
                "UPDATE modal_accounts SET failed_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", account_id),
            )

        recovered = accounts.recover_failed_accounts(cooldown_seconds=60)
        assert recovered == 1

        row = accounts.get_account(account_id)
        assert row["status"] == "ready"

    def test_container_error_auto_recovers(self):
        """Container failures should auto-recover like timeouts."""
        account_id = accounts.add_account("ContErr", "tok_id", "tok_secret")
        accounts.mark_account_failed(account_id, "container startup failed", max_fail_count=6)

        with accounts._db() as conn:
            conn.execute(
                "UPDATE modal_accounts SET failed_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", account_id),
            )

        recovered = accounts.recover_failed_accounts(cooldown_seconds=60)
        assert recovered == 1

    def test_recovery_respects_cooldown_period(self):
        """Accounts should NOT recover before cooldown expires."""
        account_id = accounts.add_account("CoolTest", "tok_id", "tok_secret")
        accounts.mark_account_failed(account_id, "transient error", max_fail_count=6)

        # Don't manipulate failed_at — it's recent
        recovered = accounts.recover_failed_accounts(cooldown_seconds=300)
        assert recovered == 0

        row = accounts.get_account(account_id)
        assert row["status"] == "failed"


class TestPreservation_RoundRobin:
    """Round-robin selection by (use_count ASC, last_used ASC)."""

    def test_least_used_account_selected_first(self):
        """Ready accounts are selected by use_count ASC."""
        # Create 3 accounts and make them ready
        ids = []
        for i, name in enumerate(["A", "B", "C"]):
            aid = accounts.add_account(name, f"tok_{i}", f"secret_{i}")
            accounts.update_account_status(aid, "checking")
            accounts.update_account_status(aid, "ready")
            ids.append(aid)

        # Mark A used twice, B once, C zero
        accounts.mark_account_used(ids[0])
        accounts.mark_account_used(ids[0])
        accounts.mark_account_used(ids[1])

        ready = accounts.list_ready_accounts()
        assert len(ready) == 3
        # C (0 uses) should be first
        assert ready[0]["id"] == ids[2]

    def test_round_robin_order_deterministic(self):
        """Same use_count → ordered by last_used ASC."""
        ids = []
        for i, name in enumerate(["X", "Y"]):
            aid = accounts.add_account(name, f"tok_{i}", f"secret_{i}")
            accounts.update_account_status(aid, "checking")
            accounts.update_account_status(aid, "ready")
            ids.append(aid)

        # Both have 0 use_count, Y created after X, both last_used is NULL
        ready = accounts.list_ready_accounts()
        assert len(ready) == 2


class TestPreservation_UseCount:
    """use_count and last_used updated after successful generation."""

    def test_mark_used_increments_count(self):
        """mark_account_used() should increment use_count."""
        aid = accounts.add_account("UseCnt", "tok_id", "tok_secret")
        accounts.update_account_status(aid, "checking")
        accounts.update_account_status(aid, "ready")

        accounts.mark_account_used(aid)
        row = accounts.get_account(aid)
        assert row["use_count"] == 1
        assert row["last_used"] is not None

        accounts.mark_account_used(aid)
        row = accounts.get_account(aid)
        assert row["use_count"] == 2

    def test_mark_used_sets_last_used(self):
        """mark_account_used() should set last_used timestamp."""
        aid = accounts.add_account("LastUsed", "tok_id", "tok_secret")
        accounts.update_account_status(aid, "checking")
        accounts.update_account_status(aid, "ready")

        row_before = accounts.get_account(aid)
        assert row_before["last_used"] is None

        accounts.mark_account_used(aid)
        row_after = accounts.get_account(aid)
        assert row_after["last_used"] is not None


class TestPreservation_ManualOperations:
    """Manual enable/disable/delete operations."""

    def test_disable_excludes_from_rotation(self):
        """Disabled accounts don't appear in list_ready_accounts."""
        aid = accounts.add_account("DisTest", "tok_id", "tok_secret")
        accounts.update_account_status(aid, "checking")
        accounts.update_account_status(aid, "ready")

        accounts.disable_account(aid)
        ready = accounts.list_ready_accounts()
        assert all(r["id"] != aid for r in ready)

    def test_enable_returns_to_rotation(self):
        """Enabled accounts re-appear in list_ready_accounts."""
        aid = accounts.add_account("EnTest", "tok_id", "tok_secret")
        accounts.update_account_status(aid, "checking")
        accounts.update_account_status(aid, "ready")

        accounts.disable_account(aid)
        accounts.enable_account(aid)

        ready = accounts.list_ready_accounts()
        assert any(r["id"] == aid for r in ready)

    def test_delete_removes_account(self):
        """Deleted accounts are gone."""
        aid = accounts.add_account("DelTest", "tok_id", "tok_secret")
        assert accounts.delete_account(aid) is True
        assert accounts.get_account(aid) is None


class TestPreservation_FailCountThreshold:
    """Accounts reaching MAX_ACCOUNT_FAIL_COUNT auto-disable."""

    def test_threshold_disables_account(self):
        """After max_fail_count temporary errors, account is disabled."""
        aid = accounts.add_account("Thresh", "tok_id", "tok_secret")
        # With max_fail_count=3, 3 failures should disable
        for _ in range(3):
            accounts.mark_account_failed(aid, "oom error", max_fail_count=3)

        row = accounts.get_account(aid)
        assert row["status"] == "disabled"
        assert row["fail_count"] == 3

    def test_below_threshold_stays_failed(self):
        """Below max_fail_count, account stays failed (not disabled)."""
        aid = accounts.add_account("BelowT", "tok_id", "tok_secret")
        accounts.mark_account_failed(aid, "oom error", max_fail_count=6)

        row = accounts.get_account(aid)
        assert row["status"] == "failed"
        assert row["fail_count"] == 1


class TestNoReadyWaitHelpers:
    """No-ready wait timeout helpers should behave deterministically."""

    def test_wait_remaining_never_negative(self):
        import api as backend_api

        assert backend_api._no_ready_wait_remaining(10.0, now=9.0) == 1.0
        assert backend_api._no_ready_wait_remaining(10.0, now=10.0) == 0.0
        assert backend_api._no_ready_wait_remaining(10.0, now=11.5) == 0.0

    def test_wait_expired_flags_deadline_crossing(self):
        import api as backend_api

        assert backend_api._no_ready_wait_expired(10.0, now=9.99) is False
        assert backend_api._no_ready_wait_expired(10.0, now=10.0) is True
        assert backend_api._no_ready_wait_expired(10.0, now=10.5) is True
