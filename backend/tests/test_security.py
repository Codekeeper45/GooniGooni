"""
Tests for SecurityGuard middleware.
Tests that Local Mode paths are blocked in production and allowed in local env.
No Modal, no GPU, no network required — uses TestClient directly.
"""
import os
import sys
from pathlib import Path

import pytest

# Ensure backend/ is on sys.path
BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _create_test_app(app_env: str):
    """Create a minimal FastAPI app with SecurityGuard for testing."""
    # Set env before importing
    os.environ["APP_ENV"] = app_env
    # Clear cached modules to pick up new env
    for mod in list(sys.modules.keys()):
        if mod in ("config", "middleware.security"):
            del sys.modules[mod]

    from fastapi import FastAPI
    from middleware.security import SecurityGuard

    app = FastAPI()
    app.add_middleware(SecurityGuard)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/environment")
    async def environment():
        return {"environment": app_env}

    @app.get("/comfy/system_stats")
    async def comfy_stats():
        return {"system": "stats"}

    @app.post("/comfy/prompt")
    async def comfy_prompt():
        return {"prompt_id": "123"}

    @app.get("/local/generate")
    async def local_generate():
        return {"result": "local"}

    @app.get("/api/generate")
    async def api_generate():
        return {"task_id": "abc"}

    @app.get("/search")
    async def search(mode: str = "remote"):
        return {"mode": mode}

    return app


@pytest.fixture
def production_client():
    """AsyncClient against a production-mode app."""
    import httpx
    app = _create_test_app("production")
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
def local_client():
    """AsyncClient against a local-mode app."""
    import httpx
    app = _create_test_app("development")
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
class TestSecurityGuardProduction:
    """In production, Local Mode paths must be blocked."""

    async def test_health_passes_through(self, production_client):
        resp = await production_client.get("/health")
        assert resp.status_code == 200

    async def test_environment_passes_through(self, production_client):
        resp = await production_client.get("/api/environment")
        assert resp.status_code == 200

    async def test_api_generate_passes_through(self, production_client):
        resp = await production_client.get("/api/generate")
        assert resp.status_code == 200

    async def test_comfy_system_stats_blocked(self, production_client):
        resp = await production_client.get("/comfy/system_stats")
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == "local_mode_blocked"
        assert "production" in data["detail"].lower()

    async def test_comfy_prompt_blocked(self, production_client):
        resp = await production_client.post("/comfy/prompt")
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == "local_mode_blocked"

    async def test_local_path_blocked(self, production_client):
        resp = await production_client.get("/local/generate")
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == "local_mode_blocked"

    async def test_mode_local_query_param_blocked(self, production_client):
        resp = await production_client.get("/search?mode=local")
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == "local_mode_blocked"

    async def test_mode_remote_query_param_allowed(self, production_client):
        resp = await production_client.get("/search?mode=remote")
        assert resp.status_code == 200

    async def test_blocked_response_has_user_action(self, production_client):
        resp = await production_client.get("/comfy/system_stats")
        data = resp.json()
        assert "user_action" in data
        assert "Remote Mode" in data["user_action"]


@pytest.mark.asyncio
class TestSecurityGuardLocal:
    """In local environment, ALL paths must pass through."""

    async def test_health_passes(self, local_client):
        resp = await local_client.get("/health")
        assert resp.status_code == 200

    async def test_comfy_stats_passes(self, local_client):
        resp = await local_client.get("/comfy/system_stats")
        assert resp.status_code == 200

    async def test_comfy_prompt_passes(self, local_client):
        resp = await local_client.post("/comfy/prompt")
        assert resp.status_code == 200

    async def test_local_path_passes(self, local_client):
        resp = await local_client.get("/local/generate")
        assert resp.status_code == 200

    async def test_mode_local_query_param_passes(self, local_client):
        resp = await local_client.get("/search?mode=local")
        assert resp.status_code == 200
