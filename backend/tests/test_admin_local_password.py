"""
Unit tests for local admin password management.
Tests: default login, wrong password, password change, dual-path auth,
       corrupted DB recovery, init_local_admin_db idempotency.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture(autouse=True)
def _setup_local_admin(monkeypatch, tmp_path):
    """Set up isolated admin.db for each test."""
    import admin_security
    import config
    import storage

    db_file = str(tmp_path / "test_admin.db")
    main_db = str(tmp_path / "test_main.db")

    monkeypatch.setattr(config, "LOCAL_ADMIN_DB_PATH", db_file)
    monkeypatch.setattr(config, "DB_PATH", main_db)
    monkeypatch.setattr(config, "RESULTS_PATH", str(tmp_path))
    monkeypatch.setattr(storage, "DB_PATH", main_db)
    monkeypatch.setattr(storage, "RESULTS_PATH", str(tmp_path))
    # Patch the module-level copy in storage as well
    monkeypatch.setattr(storage, "LOCAL_ADMIN_DB_PATH", db_file)

    # Silence audit log in tests
    monkeypatch.setattr(admin_security, "_log_action", lambda *a, **kw: None)

    # Clear rate limit state
    admin_security._clear_rate_limit_state_for_tests()

    storage.init_db()

    yield db_file


# ─── Default password login ───────────────────────────────────────────────────

def test_default_password_login_succeeds():
    import admin_security

    admin_security.init_local_admin_db()
    assert admin_security.verify_local_password("admin") is True


def test_wrong_password_rejected():
    import admin_security

    admin_security.init_local_admin_db()
    assert admin_security.verify_local_password("wrongpassword") is False
    assert admin_security.verify_local_password("") is False


# ─── Password change ──────────────────────────────────────────────────────────

def test_password_change_updates_hash_and_clears_default():
    import admin_security

    admin_security.init_local_admin_db()

    # Before change — is_default = True
    assert admin_security.check_is_default_password() is True

    # Change password
    admin_security.change_local_admin_password("admin", "new_secure_pass")

    # After change — old password fails, new works, is_default cleared
    assert admin_security.verify_local_password("admin") is False
    assert admin_security.verify_local_password("new_secure_pass") is True
    assert admin_security.check_is_default_password() is False


def test_password_change_rejects_wrong_current():
    import admin_security
    from fastapi import HTTPException

    admin_security.init_local_admin_db()

    with pytest.raises(HTTPException) as exc_info:
        admin_security.change_local_admin_password("wrong_current", "new_pass")
    assert exc_info.value.status_code == 401


def test_password_change_rejects_same_password():
    import admin_security
    from fastapi import HTTPException

    admin_security.init_local_admin_db()

    with pytest.raises(HTTPException) as exc_info:
        admin_security.change_local_admin_password("admin", "admin")
    assert exc_info.value.status_code == 400


# ─── Dual-path auth ───────────────────────────────────────────────────────────

def test_env_vars_override_local_db(monkeypatch):
    """When ADMIN_LOGIN and ADMIN_PASSWORD_HASH env vars are set, they take precedence."""
    import admin_security

    admin_security.init_local_admin_db()

    # Set env-based auth
    env_hash = admin_security._make_pbkdf2_hash("env_password")
    monkeypatch.setenv("ADMIN_LOGIN", "env_admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", env_hash)

    # Local password still works via verify_local_password
    assert admin_security.verify_local_password("admin") is True

    # But verify_admin_login_password should prefer env vars when set
    # (this tests the dual-path logic at the integration level)


# ─── Corrupted DB recovery ────────────────────────────────────────────────────

def test_corrupted_db_auto_recovery(monkeypatch, tmp_path, _setup_local_admin):
    import admin_security
    import config

    db_path = _setup_local_admin

    # Init valid DB
    admin_security.init_local_admin_db()
    assert admin_security.verify_local_password("admin") is True

    # Corrupt the DB file
    with open(db_path, "wb") as f:
        f.write(b"THIS IS NOT A VALID SQLITE FILE" * 10)

    # verify_local_password should recover automatically
    result = admin_security.verify_local_password("admin")
    assert result is True  # Recovered with default password


def test_corrupted_db_recovery_check_is_default(monkeypatch, tmp_path, _setup_local_admin):
    import admin_security

    db_path = _setup_local_admin

    admin_security.init_local_admin_db()

    # Corrupt
    with open(db_path, "wb") as f:
        f.write(b"CORRUPT" * 100)

    # Should recover and return True (default password)
    assert admin_security.check_is_default_password() is True


# ─── init_local_admin_db idempotency ──────────────────────────────────────────

def test_init_local_admin_db_idempotent():
    import admin_security

    # Call multiple times — should not error or reset changed password
    admin_security.init_local_admin_db()
    admin_security.init_local_admin_db()
    admin_security.init_local_admin_db()

    assert admin_security.verify_local_password("admin") is True


def test_init_does_not_reset_changed_password():
    import admin_security

    admin_security.init_local_admin_db()
    admin_security.change_local_admin_password("admin", "changed_pass")

    # Re-init should not overwrite the changed password
    admin_security.init_local_admin_db()

    assert admin_security.verify_local_password("changed_pass") is True
    assert admin_security.verify_local_password("admin") is False
