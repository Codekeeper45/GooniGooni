"""
Shared pytest options and fixtures for backend tests.
"""
import os

import httpx
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--base-url",
        action="store",
        default=os.environ.get("BACKEND_URL", ""),
        help="Base URL for live API tests.",
    )
    parser.addoption(
        "--api-key",
        action="store",
        default=os.environ.get("API_KEY", ""),
        help="API key for protected endpoints.",
    )
    parser.addoption(
        "--admin-key",
        action="store",
        default=os.environ.get("ADMIN_KEY", ""),
        help="Admin key for /admin/session and /admin/* endpoints.",
    )
    parser.addoption(
        "--request-timeout",
        action="store",
        type=float,
        default=float(os.environ.get("TEST_REQUEST_TIMEOUT", "20")),
        help="HTTP timeout (seconds) for live API tests.",
    )


@pytest.fixture(scope="session")
def base_url(request):
    value = (request.config.getoption("base_url") or "").strip()
    if not value:
        pytest.skip(
            "Live API tests require --base-url or BACKEND_URL. "
            "Skipping integration tests."
        )
    return value.rstrip("/")


@pytest.fixture(scope="session")
def api_key(request):
    return request.config.getoption("api_key")


@pytest.fixture(scope="session")
def admin_key(request):
    return request.config.getoption("admin_key")


@pytest.fixture(scope="session")
def request_timeout(request):
    return float(request.config.getoption("request_timeout"))


@pytest.fixture(scope="session")
def client(base_url, api_key, request_timeout):
    headers = {"X-API-Key": api_key} if api_key else {}
    timeout = httpx.Timeout(connect=5.0, read=request_timeout, write=request_timeout, pool=5.0)
    with httpx.Client(base_url=base_url, headers=headers, timeout=timeout) as c:
        yield c


@pytest.fixture(scope="session")
def raw_client(base_url, request_timeout):
    """
    Client without default auth headers.
    Useful for cookie/session flows.
    """
    timeout = httpx.Timeout(connect=5.0, read=request_timeout, write=request_timeout, pool=5.0)
    with httpx.Client(base_url=base_url, timeout=timeout) as c:
        yield c


@pytest.fixture
def create_generation_session(raw_client):
    def _create() -> httpx.Response:
        return raw_client.post("/auth/session")

    return _create


@pytest.fixture
def create_admin_session(raw_client, admin_key):
    def _create() -> httpx.Response:
        headers = {"x-admin-key": admin_key} if admin_key else {}
        return raw_client.post("/admin/session", headers=headers)

    return _create
