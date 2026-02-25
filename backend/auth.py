"""
API key authentication middleware.
The key is stored in Modal Secret named 'gooni-api-key' as env var API_KEY.
"""
import hmac
import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(_API_KEY_HEADER)) -> str:
    """
    FastAPI dependency — raises 403 if X-API-Key header is missing or wrong.
    Uses constant-time comparison to prevent timing attacks.
    """
    expected = os.environ.get("API_KEY", "")
    if not expected:
        # Fail-open only in local dev (no secret configured); log a warning.
        import logging
        logging.warning(
            "API_KEY environment variable is not set. "
            "All requests will be allowed. Set it via Modal Secret in production."
        )
        return ""

    if not api_key or not hmac.compare_digest(api_key.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-API-Key header.",
        )
    return api_key
