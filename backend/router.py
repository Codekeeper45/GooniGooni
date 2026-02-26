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

import os
import threading
from typing import Optional

import accounts as acc_store


# Maximum number of fallback attempts if an account fails mid-inference
MAX_FALLBACKS = 3
FAILED_ACCOUNT_COOLDOWN_SECONDS = int(os.environ.get("ACCOUNT_FAILED_COOLDOWN_SECONDS", "300"))
MAX_ACCOUNT_FAIL_COUNT = int(os.environ.get("ACCOUNT_MAX_FAIL_COUNT", "6"))

_router_lock = threading.Lock()


class NoReadyAccountError(RuntimeError):
    """Raised when no ready account is available for dispatch."""


class AccountRouter:
    """Thread-safe round-robin account picker with failure tracking."""

    @staticmethod
    def _no_ready_error() -> NoReadyAccountError:
        try:
            rows = acc_store.list_accounts()
        except Exception:
            # Fallback for bootstrap/unit-test scenarios where account storage
            # is unavailable; callers still get a deterministic domain error.
            rows = []
        if not rows:
            return NoReadyAccountError(
                "No Modal accounts configured. Add an account in Admin and run deploy."
            )

        by_status: dict[str, int] = {}
        for row in rows:
            status = row.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1
        status_summary = ", ".join(f"{k}={v}" for k, v in sorted(by_status.items()))
        return NoReadyAccountError(
            "No ready Modal accounts available. "
            f"Current statuses: {status_summary}. "
            "Wait for checking→ready or redeploy failed accounts."
        )

    def pick(self) -> dict:
        """
        Return the most appropriate ready account (least-used / least-recently-used).
        Raises NoReadyAccountError if no ready accounts exist.
        """
        acc_store.recover_failed_accounts(cooldown_seconds=FAILED_ACCOUNT_COOLDOWN_SECONDS)
        with _router_lock:
            candidates = acc_store.list_ready_accounts()
        if not candidates:
            raise self._no_ready_error()
        # list_ready_accounts already returns sorted by use_count ASC, last_used ASC
        return candidates[0]

    def pick_account(self) -> Optional[dict]:
        """
        Compatibility helper for contract-based call-sites.
        Returns None instead of raising when no ready accounts are available.
        """
        try:
            return self.pick()
        except NoReadyAccountError:
            return None

    def mark_success(self, account_id: str) -> None:
        """Record a successful dispatch."""
        acc_store.mark_account_used(account_id)

    def mark_used(self, account_id: str) -> None:
        """Alias kept for compatibility with older call-sites/tests."""
        self.mark_success(account_id)

    def mark_failed(self, account_id: str, error: str) -> None:
        """
        Record an account failure.
        Account is temporarily excluded and auto-recovers after cooldown.
        Repeated failures can auto-disable account when threshold is reached.
        """
        acc_store.mark_account_failed(
            account_id,
            error,
            max_fail_count=MAX_ACCOUNT_FAIL_COUNT,
        )

    def pick_with_fallback(self, tried: Optional[list[str]] = None) -> dict:
        """
        Pick a ready account, skipping any already tried in this request.
        Raises NoReadyAccountError if all candidates are exhausted.
        """
        tried = tried or []
        acc_store.recover_failed_accounts(cooldown_seconds=FAILED_ACCOUNT_COOLDOWN_SECONDS)
        with _router_lock:
            candidates = acc_store.list_ready_accounts()
        # Exclude already-tried accounts
        remaining = [c for c in candidates if c["id"] not in tried]
        if not remaining:
            if not candidates:
                raise self._no_ready_error()
            raise NoReadyAccountError(f"All {len(tried)} ready account(s) failed for this request.")
        return remaining[0]


# Singleton — import and use `router` directly
router = AccountRouter()
