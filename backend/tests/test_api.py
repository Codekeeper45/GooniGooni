"""
Smoke tests for the Gooni Gooni Backend API.
Run against a deployed (or served) Modal instance.

Usage:
    pip install httpx pytest
    pytest backend/tests/test_api.py -v \
        --base-url https://YOUR_WORKSPACE--gooni-api.modal.run \
        --api-key YOUR_SECRET_KEY

Or set env vars:
    export BACKEND_URL=https://...
    export API_KEY=...
    pytest backend/tests/test_api.py -v
"""
import os
import time

import httpx
import pytest


# ─── Config ───────────────────────────────────────────────────────────────────

def pytest_addoption(parser):
    parser.addoption("--base-url", default=os.environ.get("BACKEND_URL", "http://localhost:8000"))
    parser.addoption("--api-key", default=os.environ.get("API_KEY", ""))


@pytest.fixture(scope="session")
def base_url(request):
    return request.config.getoption("--base-url").rstrip("/")


@pytest.fixture(scope="session")
def api_key(request):
    return request.config.getoption("--api-key")


@pytest.fixture(scope="session")
def client(base_url, api_key):
    headers = {"X-API-Key": api_key} if api_key else {}
    with httpx.Client(base_url=base_url, headers=headers, timeout=30) as c:
        yield c


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestAuth:
    def test_gallery_without_key_returns_403(self, base_url):
        """Endpoints should reject requests without X-API-Key."""
        r = httpx.get(f"{base_url}/gallery")
        assert r.status_code == 403

    def test_models_without_key_returns_403(self, base_url):
        r = httpx.get(f"{base_url}/models")
        assert r.status_code == 403


class TestModels:
    def test_models_list_has_four_entries(self, client):
        r = client.get("/models")
        assert r.status_code == 200
        data = r.json()
        assert "models" in data
        assert len(data["models"]) == 4

    def test_model_schema_fields(self, client):
        r = client.get("/models")
        for model in r.json()["models"]:
            assert "id" in model
            assert "type" in model
            assert "modes" in model
            assert "parameters_schema" in model

    def test_all_model_ids_present(self, client):
        r = client.get("/models")
        ids = {m["id"] for m in r.json()["models"]}
        assert ids == {"anisora", "phr00t", "pony", "flux"}


class TestGallery:
    def test_gallery_returns_valid_structure(self, client):
        r = client.get("/gallery")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "has_more" in data

    def test_gallery_pagination(self, client):
        r = client.get("/gallery", params={"page": 1, "per_page": 5})
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert data["per_page"] == 5
        assert len(data["items"]) <= 5

    def test_gallery_model_filter(self, client):
        r = client.get("/gallery", params={"model": "anisora"})
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["model"] == "anisora"


class TestGenerateFlow:
    """
    Integration test: POST /generate → poll /status → check /results.
    Requires a running GPU backend. Skipped if no API_KEY is set
    (because that usually means we're in CI without Modal access).
    """

    @pytest.fixture(autouse=True)
    def skip_without_key(self, api_key):
        if not api_key:
            pytest.skip("API_KEY not set — skipping live generation test")

    def test_text_to_video_flow_status_transitions(self, client):
        """Submit a minimal t2v job and verify it transitions through expected states."""
        payload = {
            "model": "anisora",
            "type": "video",
            "mode": "t2v",
            "prompt": "a simple test animation, minimal",
            "width": 512,
            "height": 512,
            "num_frames": 17,
            "fps": 8,
            "seed": 42,
        }
        gen_r = client.post("/generate", json=payload)
        assert gen_r.status_code == 202, gen_r.text

        data = gen_r.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        task_id = data["task_id"]

        # Poll for up to 15 minutes
        deadline = time.time() + 900
        final_status = None
        while time.time() < deadline:
            st_r = client.get(f"/status/{task_id}", timeout=15)
            assert st_r.status_code == 200
            st = st_r.json()

            assert "status" in st
            assert "progress" in st
            assert 0 <= st["progress"] <= 100

            if st["status"] in ("done", "failed"):
                final_status = st["status"]
                break

            time.sleep(10)

        assert final_status == "done", f"Job ended with status: {final_status}"

        # Verify result is downloadable
        res_r = client.get(f"/results/{task_id}", timeout=30)
        assert res_r.status_code == 200
        assert "video" in res_r.headers["content-type"]
        assert len(res_r.content) > 1000  # At least 1 KB

        # Verify preview
        prev_r = client.get(f"/preview/{task_id}", timeout=10)
        assert prev_r.status_code == 200
        assert "image" in prev_r.headers["content-type"]

    def test_delete_gallery_item(self, client):
        """Create a minimal image task and delete it."""
        payload = {
            "model": "pony",
            "type": "image",
            "mode": "txt2img",
            "prompt": "test, simple background",
            "width": 512,
            "height": 512,
            "steps": 10,
            "seed": 1,
        }
        gen_r = client.post("/generate", json=payload)
        assert gen_r.status_code == 202
        task_id = gen_r.json()["task_id"]

        # Poll until done
        deadline = time.time() + 300
        while time.time() < deadline:
            st = client.get(f"/status/{task_id}").json()
            if st["status"] in ("done", "failed"):
                break
            time.sleep(5)

        del_r = client.delete(f"/gallery/{task_id}")
        assert del_r.status_code == 200
        body = del_r.json()
        assert body["deleted"] is True
        assert body["id"] == task_id

        # Should be gone now
        st_r = client.get(f"/status/{task_id}")
        assert st_r.status_code == 404
