"""
Unit tests for backend/auth.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class DummyRequest:
    def __init__(self, cookies: dict[str, str] | None = None):
        self.cookies = cookies or {}


@pytest.fixture(autouse=True)
def setup_tmp_db(tmp_path, monkeypatch):
    import config
    import storage

    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "RESULTS_PATH", str(tmp_path))
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    monkeypatch.setattr(storage, "RESULTS_PATH", str(tmp_path))
    storage.init_db()


def test_verify_api_key_accepts_valid_header(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    from auth import verify_api_key

    assert verify_api_key(header_key="secret-key", query_key=None) == "secret-key"


def test_verify_api_key_rejects_missing(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    from auth import verify_api_key

    with pytest.raises(HTTPException) as exc:
        verify_api_key(header_key=None, query_key=None)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "invalid_api_key"


def test_verify_api_key_allow_unauthenticated_opt_in(monkeypatch):
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED", "1")
    monkeypatch.setenv("APP_ENV", "development")
    from auth import verify_api_key

    assert verify_api_key(header_key=None, query_key=None) == ""


def test_verify_api_key_blocks_allow_unauthenticated_in_prod(monkeypatch):
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED", "1")
    monkeypatch.setenv("APP_ENV", "production")
    from auth import verify_api_key

    with pytest.raises(HTTPException) as exc:
        verify_api_key(header_key=None, query_key=None)
    assert exc.value.status_code == 500
    assert exc.value.detail["code"] == "server_misconfigured"


def test_verify_generation_session_cookie_success(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    import storage
    from auth import verify_generation_session, GENERATION_SESSION_COOKIE

    token, _ = storage.create_generation_session(ttl_seconds=3600)
    req = DummyRequest(cookies={GENERATION_SESSION_COOKIE: token})

    assert verify_generation_session(req, header_key=None, query_key=None) == token


def test_verify_generation_session_fallback_to_api_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    from auth import verify_generation_session

    req = DummyRequest()
    assert verify_generation_session(req, header_key="secret-key", query_key=None) == "secret-key"


def test_verify_generation_session_prefers_header_over_cookie(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    import storage
    from auth import verify_generation_session, GENERATION_SESSION_COOKIE

    token, _ = storage.create_generation_session(ttl_seconds=3600)
    req = DummyRequest(cookies={GENERATION_SESSION_COOKIE: token})
    # Header/query auth has higher priority than cookie session.
    with pytest.raises(HTTPException) as exc:
        verify_generation_session(req, header_key="wrong", query_key=None)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "invalid_api_key"


def test_verify_generation_session_missing_cookie(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    from auth import verify_generation_session

    req = DummyRequest()
    with pytest.raises(HTTPException) as exc:
        verify_generation_session(req, header_key=None, query_key=None)
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "generation_session_missing"


def test_verify_generation_session_invalid_key_when_no_cookie(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    from auth import verify_generation_session

    req = DummyRequest()
    with pytest.raises(HTTPException) as exc:
        verify_generation_session(req, header_key="bad-key", query_key=None)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "invalid_api_key"


def test_admin_session_expires_after_idle_timeout():
    import storage

    token, _ = storage.create_admin_session(idle_timeout_seconds=1)
    active, reason, _ = storage.validate_admin_session(token, touch=False)
    assert active is True
    assert reason is None

    time.sleep(1.2)
    active, reason, _ = storage.validate_admin_session(token, touch=False)
    assert active is False
    assert reason == "expired"
