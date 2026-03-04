"""
SecurityGuard middleware — blocks Local Mode requests in production.

In production environment, any request path containing /comfy/ or /local/,
or query parameter mode=local, returns 403 Forbidden with structured error.
All blocked attempts are logged with timestamp, IP, path, method, user-agent.
"""

import logging
from urllib.parse import parse_qs

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import get_environment

logger = logging.getLogger("security_guard")


class SecurityGuard(BaseHTTPMiddleware):
    """
    FastAPI middleware that blocks Local Mode API access in production.
    Passes through all requests in local environment.
    """

    async def dispatch(self, request: Request, call_next):
        env = get_environment()

        # In local environment, allow everything
        if env != "production":
            return await call_next(request)

        # Check if this is a local mode request
        path = request.url.path.lower()
        blocked = False
        reason = ""

        if "/comfy/" in path:
            blocked = True
            reason = f"Blocked /comfy/ path: {path}"
        elif "/local/" in path:
            blocked = True
            reason = f"Blocked /local/ path: {path}"
        else:
            # Check query parameter mode=local
            query_string = str(request.url.query)
            params = parse_qs(query_string)
            mode_values = params.get("mode", [])
            if "local" in [v.lower() for v in mode_values]:
                blocked = True
                reason = f"Blocked mode=local query param on {path}"

        if blocked:
            # Log blocked attempt
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            logger.warning(
                "SecurityGuard BLOCKED: %s | ip=%s | method=%s | path=%s | user-agent=%s",
                reason,
                client_ip,
                request.method,
                path,
                user_agent,
            )

            return JSONResponse(
                status_code=403,
                content={
                    "code": "local_mode_blocked",
                    "detail": "Local Mode is not available in production environment",
                    "user_action": "Use Remote Mode for image generation.",
                },
            )

        return await call_next(request)
