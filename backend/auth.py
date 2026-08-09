"""Header-only API key authentication."""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(header_key: str | None = Security(_API_KEY_HEADER)) -> str:
    expected = os.environ.get("API_KEY", "")
    if not expected:
        if os.environ.get("ALLOW_UNAUTHENTICATED") == "1":
            return ""
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server API key is not configured",
        )
    if not header_key or not hmac.compare_digest(header_key, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-API-Key header",
        )
    return header_key
