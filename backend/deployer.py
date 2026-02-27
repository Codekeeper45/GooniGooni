"""
Deployer — runs `modal deploy` with per-account credentials.

Each account has its own MODAL_TOKEN_ID + MODAL_TOKEN_SECRET.
We spawn a subprocess with those env vars injected so that
`modal deploy` authenticates as that specific workspace.

The deploy runs in a background thread so the API response is not blocked.
Status transitions:
  pending → (deploy running) → ready
                             → failed
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import logging
import time
from pathlib import Path
from typing import Optional

import accounts as acc_store
import httpx

# Path to the main Modal app file (relative to repo root)
BACKEND_DIR = Path(__file__).parent
APP_FILE = str(BACKEND_DIR / "app.py")
logger = logging.getLogger("deployer")
MODAL_TARGET_ENV = (os.environ.get("MODAL_TARGET_ENV", "main").strip() or "main")

_SHARED_SECRET_BINDINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gooni-api-key", ("API_KEY",)),
    ("gooni-admin", ("ADMIN_LOGIN", "ADMIN_PASSWORD_HASH")),
    ("gooni-accounts", ("ACCOUNTS_ENCRYPT_KEY",)),
    ("huggingface", ("HF_TOKEN",)),
)


def required_shared_env_keys() -> tuple[str, ...]:
    seen: list[str] = []
    for _, keys in _SHARED_SECRET_BINDINGS:
        for key in keys:
            if key not in seen:
                seen.append(key)
    return tuple(seen)


def get_missing_shared_env_keys() -> list[str]:
    missing: list[str] = []
    for key in required_shared_env_keys():
        if not os.environ.get(key, "").strip():
            missing.append(key)
    return missing


def _redact_sensitive_text(text: str, account: Optional[dict] = None) -> str:
    redacted = text
    secrets: list[str] = []
    for key in required_shared_env_keys():
        value = os.environ.get(key, "").strip()
        if value:
            secrets.append(value)
    if account:
        for key in ("token_id", "token_secret"):
            value = str(account.get(key, "")).strip()
            if value:
                secrets.append(value)

    for value in secrets:
        # Avoid masking generic short strings.
        if len(value) >= 6:
            redacted = redacted.replace(value, "***")
    return redacted


def _extract_subprocess_error(result: subprocess.CompletedProcess, account: Optional[dict]) -> str:
    raw = result.stderr or result.stdout or "Unknown deploy error"
    return _redact_sensitive_text(raw, account)[:500]


def _sync_workspace_secrets(env: dict[str, str], account: dict) -> None:
    missing = get_missing_shared_env_keys()
    if missing:
        raise RuntimeError(
            "Missing required shared env: " + ", ".join(missing)
        )

    for secret_name, env_keys in _SHARED_SECRET_BINDINGS:
        key_values = [f"{env_key}={os.environ[env_key].strip()}" for env_key in env_keys]
        cmd = [
            sys.executable,
            "-m",
            "modal",
            "secret",
            "create",
            "-e",
            MODAL_TARGET_ENV,
            "--force",
            secret_name,
            *key_values,
        ]
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode != 0:
            error = _extract_subprocess_error(result, account)
            raise RuntimeError(f"Secret sync failed for {secret_name}: {error}")


def deploy_account(account_id: str) -> None:
    """
    Deploy backend/app.py using the account's Modal credentials.
    Updates account status to 'ready' or 'failed'.
    Should be called in a background thread (non-blocking for the caller).
    """
    account = acc_store.get_account(account_id)
    if account is None:
        return

    # Minimal env: only pass what modal deploy actually needs.
    # Never forward parent secrets (API_KEY, ADMIN_KEY, ACCOUNTS_ENCRYPT_KEY, etc.).
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/root"),
        "MODAL_TOKEN_ID": account["token_id"],
        "MODAL_TOKEN_SECRET": account["token_secret"],
    }

    def _commit_volume() -> None:
        try:
            import modal as _modal
            _modal.Volume.from_name("results").commit()
        except Exception:
            pass  # best-effort; container-local reads remain consistent

    try:
        acc_store.update_account_status(account_id, "checking", error=None)
        _commit_volume()
        try:
            _sync_workspace_secrets(env, account)
        except Exception as exc:
            acc_store.mark_account_failed(
                account_id,
                _redact_sensitive_text(str(exc), account)[:500],
                failure_type="config_failed",
            )
            _commit_volume()
            return

        result = subprocess.run(
            [sys.executable, "-m", "modal", "deploy", "-e", MODAL_TARGET_ENV, APP_FILE],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,  # 2 min deploy timeout (reduced from 5 min)
        )

        if result.returncode == 0:
            # Try to extract workspace name from output
            workspace = _extract_workspace(result.stdout)
            if not workspace:
                acc_store.update_account_status(
                    account_id, "failed", error="Deploy succeeded but workspace was not detected"
                )
                _commit_volume()
                return

            ok, health_error = _wait_for_workspace_health(workspace, account_id=account_id)
            if not ok:
                failure_type, _ = acc_store._classify_error(health_error or "health check failed")
                acc_store.mark_account_failed(
                    account_id,
                    health_error or "health check failed",
                    failure_type=failure_type,
                )
                _commit_volume()
                return

            acc_store.update_account_status(account_id, "ready", workspace=workspace, error=None)
            _commit_volume()
        else:
            error = _extract_subprocess_error(result, account)
            failure_type, _ = acc_store._classify_error(error)
            acc_store.mark_account_failed(
                account_id,
                error,
                failure_type=failure_type,
            )
            _commit_volume()

    except subprocess.TimeoutExpired:
        acc_store.mark_account_failed(
            account_id,
            "Deploy timed out after 2 minutes",
            failure_type="timeout",
        )
        _commit_volume()
    except Exception as exc:
        error = _redact_sensitive_text(str(exc), account)[:500]
        failure_type, _ = acc_store._classify_error(error)
        acc_store.mark_account_failed(
            account_id,
            error,
            failure_type=failure_type,
        )
        _commit_volume()


def deploy_account_async(account_id: str) -> threading.Thread:
    """
    Kick off deploy_account in a background thread.
    Returns the thread (already started).
    """
    thread = threading.Thread(
        target=deploy_account,
        args=(account_id,),
        daemon=True,
        name=f"deploy-{account_id[:8]}",
    )
    thread.start()
    return thread


def deploy_all_accounts() -> list[threading.Thread]:
    """
    Redeploy ALL ready (and failed) accounts simultaneously.
    Skips accounts that are 'disabled'.
    Returns list of started threads.
    """
    all_accounts = acc_store.list_accounts()
    threads = []
    for account in all_accounts:
        if account["status"] in {"disabled", "checking"}:
            continue
        thread = deploy_account_async(account["id"])
        threads.append(thread)
    return threads


def _extract_workspace(output: str) -> Optional[str]:
    """
    Try to extract the workspace name from `modal deploy` stdout.
    Modal typically prints something like:
      ✓ Deployed app at https://WORKSPACE--gooni-api.modal.run
    """
    for line in output.splitlines():
        if "modal.run" in line:
            # Extract WORKSPACE from https://WORKSPACE--gooni-api.modal.run
            try:
                url = [w for w in line.split() if "modal.run" in w][0]
                workspace = url.split("//")[1].split("--")[0]
                return workspace
            except (IndexError, ValueError):
                pass
    return None


def _wait_for_workspace_health(
    workspace: str,
    account_id: Optional[str] = None,
    attempts: int = 6,
    interval_seconds: float = 5.0,
    cache_ttl_seconds: int = 300,
) -> tuple[bool, Optional[str]]:
    """
    Wait for workspace health check to pass.

    If account_id is provided, health check results are cached in the DB.
    A cached positive result younger than cache_ttl_seconds is returned
    immediately without making HTTP requests.
    """
    # Check cache first
    if account_id:
        account = acc_store.get_account(account_id)
        if account and account.get("last_health_check") and account.get("health_check_result") == "ok":
            from datetime import datetime, timezone
            try:
                cached_at = datetime.fromisoformat(account["last_health_check"])
                if cached_at.tzinfo is None:
                    cached_at = cached_at.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                if age < cache_ttl_seconds:
                    logger.info("workspace health check cache hit: %s (age=%.0fs)", workspace, age)
                    return True, None
            except Exception:
                pass  # Cache miss on malformed timestamp

    url = f"https://{workspace}--gooni-api.modal.run/health"
    timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
    last_error = "health-check did not run"
    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url)
            if response.status_code == 200:
                payload = response.json()
                if payload.get("ok") is True:
                    logger.info("workspace health check passed: %s", workspace)
                    if account_id:
                        acc_store.update_health_check(account_id, "ok")
                    return True, None
            last_error = f"health-check status={response.status_code}"
        except Exception as exc:
            last_error = f"health-check error: {exc}"
        if attempt < attempts:
            time.sleep(interval_seconds)

    # Cache negative result
    if account_id:
        acc_store.update_health_check(account_id, f"failed: {last_error}")

    return False, last_error
