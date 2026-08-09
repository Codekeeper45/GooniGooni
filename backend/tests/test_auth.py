"""Authentication behavior tests."""
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from auth import verify_api_key


def test_valid_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    assert verify_api_key("secret") == "secret"


def test_missing_or_wrong_key_is_rejected(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    with pytest.raises(HTTPException) as missing:
        verify_api_key(None)
    assert missing.value.status_code == 403
    with pytest.raises(HTTPException) as wrong:
        verify_api_key("wrong")
    assert wrong.value.status_code == 403


def test_unconfigured_server_fails_closed(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED", raising=False)
    with pytest.raises(HTTPException) as error:
        verify_api_key(None)
    assert error.value.status_code == 503


def test_explicit_local_dev_mode(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED", "1")
    assert verify_api_key(None) == ""
