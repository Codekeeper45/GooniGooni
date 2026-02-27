"""
Unit tests for backend/admin_security.py
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class _DummyClient:
    def __init__(self, host: str = "127.0.0.1"):
        self.host = host


class DummyRequest:
    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        host: str = "127.0.0.1",
    ):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.client = _DummyClient(host)


@pytest.fixture(autouse=True)
def _reset_rate_limiter(monkeypatch, tmp_path):
    import admin_security
    import config
    import storage

    db_file = str(tmp_path / "test_admin.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "RESULTS_PATH", str(tmp_path))
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    monkeypatch.setattr(storage, "RESULTS_PATH", str(tmp_path))
    storage.init_db()

    admin_security._clear_rate_limit_state_for_tests()
    monkeypatch.setattr(admin_security, "_log_action", lambda *args, **kwargs: None)


def test_verify_admin_key_header_accepts_valid(monkeypatch):
    from admin_security import verify_admin_key_header

    monkeypatch.setenv("ADMIN_KEY", "x" * 24)
    dep = verify_admin_key_header()
    req = DummyRequest()

    ip = asyncio.run(dep(req, x_admin_key="x" * 24))
    assert ip == "127.0.0.1"


def test_verify_admin_key_header_rejects_invalid(monkeypatch):
    from admin_security import verify_admin_key_header

    monkeypatch.setenv("ADMIN_KEY", "x" * 24)
    dep = verify_admin_key_header()
    req = DummyRequest()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(req, x_admin_key="wrong-key"))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "admin_key_invalid"


def test_get_admin_auth_accepts_cookie_session(monkeypatch):
    import storage
    from admin_security import ADMIN_SESSION_COOKIE, get_admin_auth

    monkeypatch.setenv("ADMIN_KEY", "x" * 24)
    token, _ = storage.create_admin_session(idle_timeout_seconds=3600)

    dep = get_admin_auth("list_accounts")
    req = DummyRequest(cookies={ADMIN_SESSION_COOKIE: token})

    ip = asyncio.run(dep(req, x_admin_key=""))
    assert ip == "127.0.0.1"


def test_get_admin_auth_requires_cookie_or_header(monkeypatch):
    from admin_security import get_admin_auth

    monkeypatch.setenv("ADMIN_KEY", "x" * 24)
    dep = get_admin_auth("list_accounts")
    req = DummyRequest()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(req, x_admin_key=""))
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "admin_session_missing"


def test_rate_limit_threshold_enforced(monkeypatch):
    import admin_security
    from admin_security import verify_admin_key_header

    monkeypatch.setenv("ADMIN_KEY", "x" * 24)
    monkeypatch.setattr(admin_security, "RATE_LIMIT", 2)

    dep = verify_admin_key_header()
    req = DummyRequest(host="10.0.0.5")

    asyncio.run(dep(req, x_admin_key="x" * 24))
    asyncio.run(dep(req, x_admin_key="x" * 24))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(req, x_admin_key="x" * 24))
    assert exc.value.status_code == 429


def test_rate_limit_precedence_over_bad_key(monkeypatch):
    import admin_security
    from admin_security import verify_admin_key_header

    monkeypatch.setenv("ADMIN_KEY", "x" * 24)
    monkeypatch.setattr(admin_security, "RATE_LIMIT", 1)

    dep = verify_admin_key_header()
    req = DummyRequest(host="10.0.0.7")

    asyncio.run(dep(req, x_admin_key="x" * 24))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(req, x_admin_key="bad"))

    # Current policy: throttle check runs first and deterministically returns 429.
    assert exc.value.status_code == 429


def _make_pbkdf2_hash(password: str, salt: str = "salt123", iterations: int = 200000) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def test_verify_admin_login_password_accepts_pbkdf2(monkeypatch):
    from admin_security import verify_admin_login_password

    monkeypatch.setenv("ADMIN_LOGIN", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _make_pbkdf2_hash("secret-pass"))
    monkeypatch.delenv("ADMIN_KEY", raising=False)

    req = DummyRequest()
    ip = verify_admin_login_password(req, "admin", "secret-pass")
    assert ip == "127.0.0.1"


def test_verify_admin_login_password_rejects_invalid(monkeypatch):
    from admin_security import verify_admin_login_password

    monkeypatch.setenv("ADMIN_LOGIN", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _make_pbkdf2_hash("secret-pass"))
    monkeypatch.delenv("ADMIN_KEY", raising=False)

    req = DummyRequest()
    with pytest.raises(HTTPException) as exc:
        verify_admin_login_password(req, "admin", "wrong-pass")
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "admin_credentials_invalid"


def test_verify_admin_login_password_legacy_mode(monkeypatch):
    from admin_security import verify_admin_login_password

    monkeypatch.delenv("ADMIN_LOGIN", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("ADMIN_KEY", "x" * 24)

    req = DummyRequest()
    ip = verify_admin_login_password(req, "admin", "x" * 24)
    assert ip == "127.0.0.1"
