"""
API key authentication middleware.
The key is stored in Modal Secret named 'gooni-api-key' as env var API_KEY.
"""
import hmac
import os

from fastapi import HTTPException, Query, Request, Security, status
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
GENERATION_SESSION_COOKIE = "gg_session"


def _reload_results_volume() -> None:
    """Best-effort volume reload before SQLite reads."""
    try:
        import modal

        modal.Volume.from_name("results").reload()
    except Exception:
        # Local/unit-test mode or non-Modal runtime.
        pass


def _auth_error(
    *,
    code: str,
    detail: str,
    user_action: str,
    status_code: int = status.HTTP_401_UNAUTHORIZED,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "detail": detail, "user_action": user_action},
    )


def _is_local_unsecured_mode() -> bool:
    """Allow unauthenticated mode only in local/dev/test runtime."""
    app_env = (os.environ.get("APP_ENV") or "").strip().lower()
    if app_env in {"local", "dev", "development", "test"}:
        return True
    return False


def verify_api_key(
    header_key: str = Security(_API_KEY_HEADER),
    query_key: str = Query(None, alias="api_key"),
) -> str:
    """
    FastAPI dependency that raises on missing/invalid API key.
    Accepts the key via X-API-Key header OR ?api_key= query param.
    Query param support is required for <video src> / <img src> tags in the browser,
    which cannot send custom headers. Inter-account proxying uses headers.
    Uses constant-time comparison to avoid timing attacks.
    """
    expected = os.environ.get("API_KEY", "")
    if not expected:
        # Fail-closed by default. Local bypass must be explicit.
        if os.environ.get("ALLOW_UNAUTHENTICATED") == "1":
            if not _is_local_unsecured_mode():
                raise _auth_error(
                    code="server_misconfigured",
                    detail="ALLOW_UNAUTHENTICATED is restricted to local/test environments.",
                    user_action="Disable ALLOW_UNAUTHENTICATED and set API_KEY.",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            return ""
        raise _auth_error(
            code="server_misconfigured",
            detail="Server misconfigured: API_KEY is not set.",
            user_action="Contact support and verify backend secrets configuration.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    api_key = header_key or query_key
    if not api_key or not hmac.compare_digest(api_key.encode(), expected.encode()):
        raise _auth_error(
            code="invalid_api_key",
            detail="Invalid or missing X-API-Key.",
            user_action="Refresh the page and create a new session.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return api_key


def verify_generation_session(
    request: Request,
    header_key: str = Security(_API_KEY_HEADER),
    query_key: str = Query(None, alias="api_key"),
) -> str:
    """
    Browser path auth for generation endpoints.
    Priority:
      1) Valid API key (backward compatibility + server-to-server)
      2) Valid cookie session (`gg_session`)
    """
    if header_key or query_key:
        return verify_api_key(header_key=header_key, query_key=query_key)

    token = request.cookies.get(GENERATION_SESSION_COOKIE, "")
    if not token:
        raise _auth_error(
            code="generation_session_missing",
            detail="Generation session is missing.",
            user_action="Request a new generation session and retry.",
        )

    import storage

    _reload_results_volume()
    active, reason, _ = storage.validate_generation_session(token)
    if not active:
        reason_code = "generation_session_expired" if reason == "expired" else "generation_session_invalid"
        raise _auth_error(
            code=reason_code,
            detail="Generation session is invalid or expired.",
            user_action="Create a new generation session and retry.",
        )

    return token
