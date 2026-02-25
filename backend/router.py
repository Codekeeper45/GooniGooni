"""
AccountRouter — round-robin multi-account dispatch with failover.

Rotation rules:
  1. Only 'ready' accounts participate in rotation
  2. Round-robin by (use_count ASC, last_used ASC)  — i.e. least recently / least used first
  3. On account failure: mark it 'failed', try next candidate (up to MAX_FALLBACKS)
  4. After MAX_FALLBACKS exhausted → raise NoReadyAccountError

The router is stateless at module level; it reads account state fresh from
the DB on every pick() call so that status changes (new account goes ready,
admin disables an account) are picked up without restart.
"""
from __future__ import annotations

import threading
from typing import Optional

import accounts as acc_store


# Maximum number of fallback attempts if an account fails mid-inference
MAX_FALLBACKS = 3

_router_lock = threading.Lock()


class NoReadyAccountError(RuntimeError):
    """Raised when no ready account is available for dispatch."""


class AccountRouter:
    """Thread-safe round-robin account picker with failure tracking."""

    def pick(self) -> dict:
        """
        Return the most appropriate ready account (least-used / least-recently-used).
        Raises NoReadyAccountError if no ready accounts exist.
        """
        with _router_lock:
            candidates = acc_store.list_ready_accounts()
        if not candidates:
            raise NoReadyAccountError(
                "No ready Modal accounts available. "
                "Add an account via the Admin panel and wait for it to deploy."
            )
        # list_ready_accounts already returns sorted by use_count ASC, last_used ASC
        return candidates[0]

    def mark_success(self, account_id: str) -> None:
        """Record a successful dispatch."""
        acc_store.mark_account_used(account_id)

    def mark_failed(self, account_id: str, error: str) -> None:
        """
        Record an account failure.
        The account stays in 'failed' status and is excluded from rotation
        until an admin manually re-deploys it.
        """
        acc_store.update_account_status(account_id, "failed", error=error)

    def pick_with_fallback(self, tried: Optional[list[str]] = None) -> dict:
        """
        Pick a ready account, skipping any already tried in this request.
        Raises NoReadyAccountError if all candidates are exhausted.
        """
        tried = tried or []
        with _router_lock:
            candidates = acc_store.list_ready_accounts()
        # Exclude already-tried accounts
        remaining = [c for c in candidates if c["id"] not in tried]
        if not remaining:
            raise NoReadyAccountError(
                f"All {len(tried)} available account(s) failed for this request."
            )
        return remaining[0]


# Singleton — import and use `router` directly
router = AccountRouter()
