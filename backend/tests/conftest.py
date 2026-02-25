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
def client(base_url, api_key):
    headers = {"X-API-Key": api_key} if api_key else {}
    with httpx.Client(base_url=base_url, headers=headers, timeout=30) as c:
        yield c
