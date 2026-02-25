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
from pathlib import Path
from typing import Optional

import accounts as acc_store

# Path to the main Modal app file (relative to repo root)
BACKEND_DIR = Path(__file__).parent
APP_FILE = str(BACKEND_DIR / "app.py")


def deploy_account(account_id: str) -> None:
    """
    Deploy backend/app.py using the account's Modal credentials.
    Updates account status to 'ready' or 'failed'.
    Should be called in a background thread (non-blocking for the caller).
    """
    account = acc_store.get_account(account_id)
    if account is None:
        return

    acc_store.update_account_status(account_id, "pending")

    # Build a clean env with the account's Modal credentials
    env = {**os.environ}
    env["MODAL_TOKEN_ID"] = account["token_id"]
    env["MODAL_TOKEN_SECRET"] = account["token_secret"]
    # Remove any existing Modal profile env to avoid conflicts
    env.pop("MODAL_PROFILE", None)

    try:
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
            acc_store.update_account_status(
                account_id,
                "ready",
                workspace=workspace,
                error=None,
            )
        else:
            error = (result.stderr or result.stdout or "Unknown deploy error")[:500]
            acc_store.update_account_status(account_id, "failed", error=error)

    except subprocess.TimeoutExpired:
        acc_store.update_account_status(
            account_id, "failed", error="Deploy timed out after 5 minutes"
        )
    except Exception as exc:
        acc_store.update_account_status(account_id, "failed", error=str(exc))


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
