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
        result = subprocess.run(
            [sys.executable, "-m", "modal", "deploy", APP_FILE],
            env=env,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min deploy timeout
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

            ok, health_error = _wait_for_workspace_health(workspace)
            if not ok:
                acc_store.update_account_status(
                    account_id,
                    "failed",
                    workspace=workspace,
                    error=health_error,
                )
                _commit_volume()
                return

            acc_store.update_account_status(account_id, "ready", workspace=workspace, error=None)
            _commit_volume()
        else:
            error = (result.stderr or result.stdout or "Unknown deploy error")[:500]
            acc_store.update_account_status(account_id, "failed", error=error)
            _commit_volume()

    except subprocess.TimeoutExpired:
        acc_store.update_account_status(
            account_id, "failed", error="Deploy timed out after 5 minutes"
        )
        _commit_volume()
    except Exception as exc:
        acc_store.update_account_status(account_id, "failed", error=str(exc))
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
        if account["status"] == "disabled":
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
    attempts: int = 12,
    interval_seconds: float = 5.0,
) -> tuple[bool, Optional[str]]:
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
                    return True, None
            last_error = f"health-check status={response.status_code}"
        except Exception as exc:
            last_error = f"health-check error: {exc}"
        if attempt < attempts:
            time.sleep(interval_seconds)
    return False, last_error
