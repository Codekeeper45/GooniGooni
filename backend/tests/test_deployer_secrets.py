"""
Unit tests for deployer secret synchronization workflow.
"""
from __future__ import annotations

import subprocess
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

    db_file = str(tmp_path / "test_deployer.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "RESULTS_PATH", str(tmp_path))
    monkeypatch.setenv("ACCOUNTS_ENCRYPT_KEY", Fernet.generate_key().decode())

    import accounts

    monkeypatch.setattr(accounts, "DB_PATH", db_file)
    monkeypatch.setattr(accounts, "RESULTS_PATH", str(tmp_path))
    accounts.init_accounts_table()
    yield


import accounts  # noqa: E402
import deployer  # noqa: E402


def _set_required_shared_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "api_shared_value")
    monkeypatch.setenv("ADMIN_LOGIN", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "pbkdf2_sha256$600000$salt$hash")
    if not (deployer.os.environ.get("ACCOUNTS_ENCRYPT_KEY") or "").strip():
        raise RuntimeError("ACCOUNTS_ENCRYPT_KEY must be configured by test fixture")
    monkeypatch.setenv("HF_TOKEN", "hf_shared_token")


def test_get_missing_shared_env_keys(monkeypatch):
    for key in deployer.required_shared_env_keys():
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("API_KEY", "present")
    missing = deployer.get_missing_shared_env_keys()
    assert missing == [
        "ADMIN_LOGIN",
        "ADMIN_PASSWORD_HASH",
        "ACCOUNTS_ENCRYPT_KEY",
        "HF_TOKEN",
    ]


def test_deploy_account_syncs_shared_secrets_before_deploy(monkeypatch):
    _set_required_shared_env(monkeypatch)
    account_id = accounts.add_account("AutoProvision", "tok_id_123", "tok_secret_123")
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if len(cmd) >= 4 and cmd[3] == "secret":
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
        if len(cmd) >= 4 and cmd[3] == "deploy":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="Deployed app at https://workspace-auto--gooni-api.modal.run",
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unexpected")

    monkeypatch.setattr(deployer.subprocess, "run", fake_run)
    monkeypatch.setattr(
        deployer,
        "_wait_for_workspace_health",
        lambda workspace, account_id=None, attempts=1, interval_seconds=0.0, cache_ttl_seconds=0: (True, None),
    )
    monkeypatch.setattr(deployer, "_trigger_workspace_warmup", lambda workspace, account_id=None: (True, None))

    deployer.deploy_account(account_id)

    row = accounts.get_account(account_id)
    assert row is not None
    assert row["status"] == "ready"
    assert row["workspace"] == "workspace-auto"

    secret_calls = [cmd for cmd in calls if len(cmd) >= 4 and cmd[3] == "secret"]
    deploy_calls = [cmd for cmd in calls if len(cmd) >= 4 and cmd[3] == "deploy"]
    assert len(secret_calls) == 4
    assert len(deploy_calls) == 1

    secret_names = {cmd[cmd.index("--force") + 1] for cmd in secret_calls}
    assert secret_names == {"gooni-api-key", "gooni-admin", "gooni-accounts", "huggingface"}
    for cmd in secret_calls:
        assert cmd[cmd.index("-e") + 1] == "main"
    assert deploy_calls[0][deploy_calls[0].index("-e") + 1] == "main"


def test_deploy_account_health_429_disables_account(monkeypatch):
    _set_required_shared_env(monkeypatch)
    account_id = accounts.add_account("QuotaHealth", "tok_id_q", "tok_secret_q")

    def fake_run(cmd, **kwargs):
        if len(cmd) >= 4 and cmd[3] == "secret":
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
        if len(cmd) >= 4 and cmd[3] == "deploy":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="Deployed app at https://workspace-quota--gooni-api.modal.run",
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unexpected")

    monkeypatch.setattr(deployer.subprocess, "run", fake_run)
    monkeypatch.setattr(
        deployer,
        "_wait_for_workspace_health",
        lambda workspace, account_id=None, attempts=1, interval_seconds=0.0, cache_ttl_seconds=0: (
            False,
            "health-check status=429: workspace billing cycle spend limit reached",
        ),
    )

    deployer.deploy_account(account_id)

    row = accounts.get_account(account_id)
    assert row is not None
    assert row["status"] == "disabled"
    assert row["failure_type"] == "quota_exceeded"


def test_deploy_account_requires_warmup_before_ready(monkeypatch):
    _set_required_shared_env(monkeypatch)
    monkeypatch.setattr(deployer, "ACCOUNT_WARMUP_REQUIRED", True)
    account_id = accounts.add_account("WarmupRequired", "tok_id_w", "tok_secret_w")

    def fake_run(cmd, **kwargs):
        if len(cmd) >= 4 and cmd[3] == "secret":
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
        if len(cmd) >= 4 and cmd[3] == "deploy":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="Deployed app at https://workspace-warmup--gooni-api.modal.run",
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unexpected")

    monkeypatch.setattr(deployer.subprocess, "run", fake_run)
    monkeypatch.setattr(deployer, "_wait_for_workspace_health", lambda workspace, account_id=None, attempts=1, interval_seconds=0.0, cache_ttl_seconds=0: (True, None))
    monkeypatch.setattr(deployer, "_trigger_workspace_warmup", lambda workspace, account_id=None: (False, "warmup failed for anisora"))

    deployer.deploy_account(account_id)

    row = accounts.get_account(account_id)
    assert row is not None
    assert row["status"] == "failed"
    assert row["failure_type"] in {"health_check_failed", "unknown"}


def test_deploy_account_masks_secret_values_on_sync_failure(monkeypatch):
    _set_required_shared_env(monkeypatch)
    hf_token = "hf_secret_token_value_123"
    monkeypatch.setenv("HF_TOKEN", hf_token)
    account_id = accounts.add_account("SyncFail", "tok_id_456", "tok_secret_456")

    def fake_run(cmd, **kwargs):
        if len(cmd) >= 4 and cmd[3] == "secret":
            secret_name = cmd[cmd.index("--force") + 1]
            if secret_name == "huggingface":
                return subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout="",
                    stderr=f"remote rejected token {hf_token}",
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="deploy should not run")

    monkeypatch.setattr(deployer.subprocess, "run", fake_run)

    deployer.deploy_account(account_id)

    row = accounts.get_account(account_id)
    assert row is not None
    assert row["status"] == "disabled"
    assert row["failure_type"] == "config_failed"
    assert "huggingface" in (row["last_error"] or "")
    assert hf_token not in (row["last_error"] or "")


def test_deploy_account_retries_before_success(monkeypatch):
    _set_required_shared_env(monkeypatch)
    monkeypatch.setattr(deployer, "ACCOUNT_DEPLOY_MAX_RETRIES", 3)
    monkeypatch.setattr(deployer, "ACCOUNT_DEPLOY_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(deployer, "ACCOUNT_DEPLOY_RETRY_MAX_BACKOFF_SECONDS", 0.0)
    account_id = accounts.add_account("RetryOnboarding", "tok_id_r", "tok_secret_r")

    deploy_attempts = {"count": 0}

    def fake_run(cmd, **kwargs):
        if len(cmd) >= 4 and cmd[3] == "secret":
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
        if len(cmd) >= 4 and cmd[3] == "deploy":
            deploy_attempts["count"] += 1
            if deploy_attempts["count"] == 1:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="temporary network issue")
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="Deployed app at https://workspace-retry--gooni-api.modal.run",
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unexpected")

    monkeypatch.setattr(deployer.subprocess, "run", fake_run)
    monkeypatch.setattr(deployer, "_wait_for_workspace_health", lambda workspace, account_id=None, attempts=1, interval_seconds=0.0, cache_ttl_seconds=0: (True, None))
    monkeypatch.setattr(deployer, "_trigger_workspace_warmup", lambda workspace, account_id=None: (True, None))

    deployer.deploy_account(account_id)

    row = accounts.get_account(account_id)
    assert row is not None
    assert row["status"] == "ready"
    assert deploy_attempts["count"] == 2
