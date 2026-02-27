"""
Unit tests for backend/router.py
Uses monkeypatching to avoid real SQLite I/O — no Modal, no GPU.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from router import AccountRouter, NoReadyAccountError


def _make_account(id_: str, use_count: int = 0, last_used: str | None = None) -> dict:
    return {
        "id": id_,
        "label": f"Account-{id_}",
        "workspace": "ws",
        "status": "ready",
        "use_count": use_count,
        "last_used": last_used,
        "last_error": None,
    }


@pytest.fixture(autouse=True)
def _stub_recovery():
    with patch("router.acc_store.recover_failed_accounts", return_value=0):
        yield


class TestRouterPick:
    def test_raises_when_no_ready_accounts(self):
        r = AccountRouter()
        with patch("router.acc_store.pick_and_mark_ready_account", return_value=None), patch(
            "router.acc_store.list_accounts", return_value=[]
        ):
            with pytest.raises(NoReadyAccountError):
                r.pick()

    def test_returns_atomically_picked_account(self):
        r = AccountRouter()
        with patch(
            "router.acc_store.pick_and_mark_ready_account",
            return_value=_make_account("a"),
        ) as mock_pick:
            picked = r.pick()
            assert picked["id"] == "a"
            mock_pick.assert_called_once_with()


class TestRouterMarkSuccess:
    def test_mark_success_is_noop(self):
        r = AccountRouter()
        with patch("router.acc_store.mark_account_used") as mock_used:
            r.mark_success("acct-1")
            mock_used.assert_not_called()


class TestRouterMarkFailed:
    def test_updates_status_to_failed(self):
        r = AccountRouter()
        with patch("router.acc_store.mark_account_failed") as mock_mark_failed:
            r.mark_failed("acct-2", "CUDA OOM")
            mock_mark_failed.assert_called_once()
            args, kwargs = mock_mark_failed.call_args
            assert args[0] == "acct-2"
            assert args[1] == "CUDA OOM"
            assert kwargs["max_fail_count"] > 0


class TestPickWithFallback:
    def test_skips_tried_accounts(self):
        r = AccountRouter()
        with patch(
            "router.acc_store.pick_and_mark_ready_account",
            return_value=_make_account("b", use_count=1),
        ) as mock_pick:
            picked = r.pick_with_fallback(tried=["a"])
            assert picked["id"] == "b"
            mock_pick.assert_called_once_with(exclude_ids=["a"])

    def test_raises_when_all_tried(self):
        all_accounts = [_make_account("a"), _make_account("b")]
        r = AccountRouter()
        with patch("router.acc_store.pick_and_mark_ready_account", return_value=None), patch(
            "router.acc_store.list_ready_accounts", return_value=all_accounts
        ):
            with pytest.raises(NoReadyAccountError):
                r.pick_with_fallback(tried=["a", "b"])

    def test_empty_tried_behaves_like_pick(self):
        r = AccountRouter()
        with patch(
            "router.acc_store.pick_and_mark_ready_account",
            return_value=_make_account("x"),
        ) as mock_pick:
            picked = r.pick_with_fallback(tried=[])
            assert picked["id"] == "x"
            mock_pick.assert_called_once_with(exclude_ids=[])

    def test_raises_when_no_accounts_at_all(self):
        r = AccountRouter()
        with patch("router.acc_store.pick_and_mark_ready_account", return_value=None), patch(
            "router.acc_store.list_ready_accounts", return_value=[]
        ), patch("router.acc_store.list_accounts", return_value=[]):
            with pytest.raises(NoReadyAccountError):
                r.pick_with_fallback()


class TestFallbackSimulation:
    """Simulate a generate flow with account failures."""

    def test_fallback_to_second_account_on_failure(self):
        """
        Simulate: pick A → dispatch fails → mark A failed → pick B.
        """
        r = AccountRouter()

        def _pick_side_effect(exclude_ids=None):
            exclude_ids = exclude_ids or []
            if "A" not in exclude_ids:
                return _make_account("A")
            if "B" not in exclude_ids:
                return _make_account("B")
            return None

        with patch(
            "router.acc_store.pick_and_mark_ready_account",
            side_effect=_pick_side_effect,
        ) as mock_pick, patch("router.acc_store.mark_account_failed") as mock_failed:
            acct = r.pick_with_fallback(tried=[])
            assert acct["id"] == "A"

            r.mark_failed("A", "timeout")
            mock_failed.assert_called_once()

            acct = r.pick_with_fallback(tried=["A"])
            assert acct["id"] == "B"
            assert mock_pick.call_count == 2
