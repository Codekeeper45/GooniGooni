"""
Unit tests for backend/router.py
Uses monkeypatching to avoid real SQLite I/O — no Modal, no GPU.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from router import AccountRouter, NoReadyAccountError


def _make_account(id_: str, use_count: int = 0) -> dict:
    return {
        "id": id_,
        "label": f"Account-{id_}",
        "token_id": "tid",
        "token_secret": "tsec",
        "workspace": "ws",
        "status": "ready",
        "use_count": use_count,
        "last_used": None,
        "last_error": None,
    }


class TestRouterPick:
    def test_raises_when_no_ready_accounts(self):
        r = AccountRouter()
        with patch("router.acc_store.list_ready_accounts", return_value=[]):
            with pytest.raises(NoReadyAccountError):
                r.pick()

    def test_returns_least_used_first(self):
        accounts = [
            _make_account("b", use_count=5),
            _make_account("a", use_count=0),
        ]
        r = AccountRouter()
        with patch("router.acc_store.list_ready_accounts", return_value=accounts):
            # list_ready_accounts is already sorted by use_count ASC in the real impl
            # Simulate sorted order
            sorted_accounts = sorted(accounts, key=lambda x: x["use_count"])
            with patch("router.acc_store.list_ready_accounts", return_value=sorted_accounts):
                picked = r.pick()
                assert picked["id"] == "a"

    def test_returns_first_of_equally_used(self):
        accounts = [_make_account("x", 3), _make_account("y", 3)]
        r = AccountRouter()
        with patch("router.acc_store.list_ready_accounts", return_value=accounts):
            picked = r.pick()
            assert picked["id"] == "x"  # first in list


class TestRouterMarkSuccess:
    def test_calls_mark_account_used(self):
        r = AccountRouter()
        with patch("router.acc_store.mark_account_used") as mock_used:
            r.mark_success("acct-1")
            mock_used.assert_called_once_with("acct-1")


class TestRouterMarkFailed:
    def test_updates_status_to_failed(self):
        r = AccountRouter()
        with patch("router.acc_store.update_account_status") as mock_update:
            r.mark_failed("acct-2", "CUDA OOM")
            mock_update.assert_called_once_with("acct-2", "failed", error="CUDA OOM")


class TestPickWithFallback:
    def test_skips_tried_accounts(self):
        all_accounts = [
            _make_account("a", use_count=0),
            _make_account("b", use_count=1),
        ]
        r = AccountRouter()
        with patch("router.acc_store.list_ready_accounts", return_value=all_accounts):
            picked = r.pick_with_fallback(tried=["a"])
            assert picked["id"] == "b"

    def test_raises_when_all_tried(self):
        all_accounts = [_make_account("a"), _make_account("b")]
        r = AccountRouter()
        with patch("router.acc_store.list_ready_accounts", return_value=all_accounts):
            with pytest.raises(NoReadyAccountError):
                r.pick_with_fallback(tried=["a", "b"])

    def test_empty_tried_behaves_like_pick(self):
        all_accounts = [_make_account("x")]
        r = AccountRouter()
        with patch("router.acc_store.list_ready_accounts", return_value=all_accounts):
            picked = r.pick_with_fallback(tried=[])
            assert picked["id"] == "x"

    def test_raises_when_no_accounts_at_all(self):
        r = AccountRouter()
        with patch("router.acc_store.list_ready_accounts", return_value=[]):
            with pytest.raises(NoReadyAccountError):
                r.pick_with_fallback()


class TestFallbackSimulation:
    """Simulate a generate flow with account failures."""

    def test_fallback_to_second_account_on_failure(self):
        """
        Simulate: pick A → dispatch fails → mark A failed → pick B → success.
        """
        _dispatched = []
        _failed = []

        accounts_list = [_make_account("A"), _make_account("B")]

        def mock_list_ready():
            return [a for a in accounts_list if a["id"] not in _failed]

        r = AccountRouter()
        tried = []

        with patch("router.acc_store.list_ready_accounts", side_effect=mock_list_ready), \
             patch("router.acc_store.mark_account_used") as mock_used, \
             patch("router.acc_store.update_account_status") as mock_status:

            # First pick → A
            acct = r.pick_with_fallback(tried=tried)
            assert acct["id"] == "A"
            tried.append("A")

            # Simulate failure on A
            _failed.append("A")
            r.mark_failed("A", "timeout")

            # Second pick → B
            acct = r.pick_with_fallback(tried=tried)
            assert acct["id"] == "B"

            # Success on B
            r.mark_success("B")
            mock_used.assert_called_once_with("B")
