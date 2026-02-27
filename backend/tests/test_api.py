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
import json

import httpx
import pytest

POLL_INTERVAL_SECONDS = int(os.environ.get("TEST_POLL_INTERVAL_SECONDS", "5"))
VIDEO_FLOW_TIMEOUT_SECONDS = int(os.environ.get("TEST_VIDEO_FLOW_TIMEOUT_SECONDS", "180"))
IMAGE_FLOW_TIMEOUT_SECONDS = int(os.environ.get("TEST_IMAGE_FLOW_TIMEOUT_SECONDS", "120"))
QUEUE_OVERLOAD_STORM_REQUESTS = int(os.environ.get("TEST_QUEUE_OVERLOAD_STORM_REQUESTS", "0"))
QUEUE_OVERLOAD_SUBMIT_INTERVAL_SECONDS = float(
    os.environ.get("TEST_QUEUE_OVERLOAD_SUBMIT_INTERVAL_SECONDS", "0.1")
)




# --- Tests -------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True


class TestAuth:
    def test_gallery_without_key_returns_auth_error(self, base_url):
        """Endpoints should reject unauthenticated requests."""
        r = httpx.get(f"{base_url}/gallery")
        assert r.status_code in (401, 403)

    def test_models_without_key_returns_auth_error(self, base_url):
        r = httpx.get(f"{base_url}/models")
        assert r.status_code in (401, 403)


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


class TestGenerationSessionContracts:
    def test_auth_session_create_and_read(self, raw_client):
        create_r = raw_client.post("/auth/session")
        assert create_r.status_code == 204, create_r.text
        assert "gg_session" in raw_client.cookies

        state_r = raw_client.get("/auth/session")
        assert state_r.status_code == 200, state_r.text
        payload = state_r.json()
        assert payload["valid"] is True
        assert payload["active"] is True
        assert "expires_at" in payload

    def test_generation_auth_boundary_requires_session_or_api_key(self, raw_client):
        no_auth_r = raw_client.get("/gallery")
        assert no_auth_r.status_code in (401, 403)

        session_r = raw_client.post("/auth/session")
        assert session_r.status_code == 204
        with_auth_r = raw_client.get("/gallery")
        assert with_auth_r.status_code == 200, with_auth_r.text

    def test_generate_without_manual_key_when_session_exists(self, raw_client):
        session_r = raw_client.post("/auth/session")
        assert session_r.status_code == 204

        payload = {
            "model": "pony",
            "type": "image",
            "mode": "txt2img",
            "prompt": "smoke test session auth",
            "width": 512,
            "height": 512,
            "steps": 5,
            "seed": 1,
        }
        generate_r = raw_client.post("/generate", json=payload)
        # 200 accepted is expected; 422 is also acceptable if backend schema changes.
        assert generate_r.status_code in (200, 422), generate_r.text

    def test_fixed_video_parameter_validation_422(self, raw_client):
        session_r = raw_client.post("/auth/session")
        assert session_r.status_code == 204

        payload = {
            "model": "anisora",
            "type": "video",
            "mode": "t2v",
            "prompt": "contract validation",
            "steps": 20,
            "width": 512,
            "height": 512,
            "seed": 1,
        }
        generate_r = raw_client.post("/generate", json=payload)
        assert generate_r.status_code == 422, generate_r.text

    def test_queue_overloaded_contract_503(self, raw_client):
        """
        Optional pressure test.
        Enable with TEST_QUEUE_OVERLOAD_STORM_REQUESTS>0.
        """
        if QUEUE_OVERLOAD_STORM_REQUESTS <= 0:
            pytest.skip("Set TEST_QUEUE_OVERLOAD_STORM_REQUESTS>0 to run overload contract test")

        session_r = raw_client.post("/auth/session")
        assert session_r.status_code == 204

        payload = {
            "model": "anisora",
            "type": "video",
            "mode": "t2v",
            "prompt": "queue overload contract",
            "width": 512,
            "height": 512,
            "num_frames": 17,
            "fps": 8,
            "seed": 1,
        }

        overloaded = False
        for _ in range(QUEUE_OVERLOAD_STORM_REQUESTS):
            r = raw_client.post("/generate", json=payload)
            assert r.status_code in (200, 503), r.text
            if r.status_code == 503:
                detail = r.json()
                assert detail.get("code") == "queue_overloaded"
                assert detail.get("metadata", {}).get("max_depth") is not None
                overloaded = True
                break
            time.sleep(QUEUE_OVERLOAD_SUBMIT_INTERVAL_SECONDS)

        assert overloaded, "Expected at least one deterministic 503 queue_overloaded response"

    def test_generate_acceptance_contract_all_models(self, raw_client):
        session_r = raw_client.post("/auth/session")
        assert session_r.status_code == 204

        payloads = [
            {
                "model": "anisora",
                "type": "video",
                "mode": "t2v",
                "prompt": "contract anisora",
                "width": 512,
                "height": 512,
                "num_frames": 17,
                "fps": 8,
                "steps": 8,
                "seed": 1,
            },
            {
                "model": "phr00t",
                "type": "video",
                "mode": "t2v",
                "prompt": "contract phr00t",
                "width": 512,
                "height": 512,
                "num_frames": 17,
                "fps": 8,
                "steps": 4,
                "cfg_scale": 1.0,
                "seed": 2,
            },
            {
                "model": "pony",
                "type": "image",
                "mode": "txt2img",
                "prompt": "contract pony",
                "width": 512,
                "height": 512,
                "steps": 8,
                "seed": 3,
            },
            {
                "model": "flux",
                "type": "image",
                "mode": "txt2img",
                "prompt": "contract flux",
                "width": 512,
                "height": 512,
                "steps": 8,
                "seed": 4,
            },
        ]

        for payload in payloads:
            r = raw_client.post("/generate", json=payload)
            assert r.status_code in (200, 503), (payload["model"], r.status_code, r.text)
            body = r.json()
            if r.status_code == 200:
                assert "task_id" in body
                assert body.get("status") == "pending"
            else:
                assert {"code", "detail", "user_action"}.issubset(set(body.keys()))

    def test_generate_validation_error_envelope_contract(self, raw_client):
        session_r = raw_client.post("/auth/session")
        assert session_r.status_code == 204

        invalid_payload = {
            "model": "anisora",
            "type": "video",
            "mode": "t2v",
            "prompt": "invalid steps",
            "width": 512,
            "height": 512,
            "steps": 20,
            "seed": 123,
        }
        r = raw_client.post("/generate", json=invalid_payload)
        assert r.status_code == 422, r.text
        body = r.json()
        assert {"code", "detail", "user_action"}.issubset(set(body.keys()))


class TestAdminSessionContracts:
    @pytest.fixture(autouse=True)
    def skip_without_admin_key(self, admin_key):
        if not admin_key:
            pytest.skip("ADMIN_KEY not set - skipping admin session tests")

    def test_admin_session_post_get_delete_flow(self, raw_client, create_admin_session):
        create_r = create_admin_session()
        assert create_r.status_code == 204, create_r.text
        assert "gg_admin_session" in raw_client.cookies

        get_r = raw_client.get("/admin/session")
        assert get_r.status_code == 200, get_r.text
        payload = get_r.json()
        assert payload["active"] is True
        assert "idle_timeout_seconds" in payload

        delete_r = raw_client.delete("/admin/session")
        assert delete_r.status_code == 204, delete_r.text

        get_after_delete = raw_client.get("/admin/session")
        assert get_after_delete.status_code in (401, 403)

    def test_admin_accounts_server_authoritative_status(self, raw_client, create_admin_session):
        create_r = create_admin_session()
        assert create_r.status_code == 204

        list_r = raw_client.get("/admin/accounts")
        assert list_r.status_code == 200, list_r.text
        payload = list_r.json()
        assert "accounts" in payload
        allowed_statuses = {"pending", "checking", "ready", "failed", "disabled"}
        for row in payload["accounts"]:
            assert row.get("status") in allowed_statuses

    def test_admin_accounts_exposes_operational_diagnostics(self, raw_client, create_admin_session):
        create_r = create_admin_session()
        assert create_r.status_code == 204

        list_r = raw_client.get("/admin/accounts")
        assert list_r.status_code == 200, list_r.text
        payload = list_r.json()
        diagnostics = payload.get("diagnostics", {})
        assert isinstance(diagnostics, dict)
        assert "queue_depth" in diagnostics
        assert "queue_overloaded_count" in diagnostics
        assert "fallback_count" in diagnostics

    def test_admin_accounts_diagnostics_do_not_leak_keys(
        self, raw_client, create_admin_session, api_key, admin_key
    ):
        create_r = create_admin_session()
        assert create_r.status_code == 204

        list_r = raw_client.get("/admin/accounts")
        assert list_r.status_code == 200, list_r.text
        serialized = json.dumps(list_r.json(), ensure_ascii=False)
        if api_key:
            assert api_key not in serialized
        if admin_key:
            assert admin_key not in serialized

    def test_admin_session_actions_are_audited(self, raw_client, admin_key, create_admin_session):
        create_r = create_admin_session()
        assert create_r.status_code == 204
        _ = raw_client.get("/admin/session")
        _ = raw_client.delete("/admin/session")

        logs_r = raw_client.get("/admin/logs", headers={"x-admin-key": admin_key})
        assert logs_r.status_code == 200, logs_r.text
        logs = logs_r.json().get("logs", [])
        actions = [entry.get("action", "") for entry in logs]
        assert any(a == "admin_session_create" for a in actions)
        assert any(a == "admin_session_get" for a in actions)
        assert any(a == "admin_session_delete" for a in actions)

    def test_admin_session_idle_timeout_probe(self, raw_client, create_admin_session):
        probe_seconds = int(os.environ.get("TEST_ADMIN_IDLE_PROBE_SECONDS", "0"))
        if probe_seconds <= 0:
            pytest.skip("TEST_ADMIN_IDLE_PROBE_SECONDS is not set; idle-timeout probe skipped")

        create_r = create_admin_session()
        assert create_r.status_code == 204

        pre_r = raw_client.get("/admin/session")
        assert pre_r.status_code == 200
        declared_timeout = int(pre_r.json().get("idle_timeout_seconds", 43200))
        if declared_timeout > probe_seconds:
            pytest.skip(
                f"Server idle timeout ({declared_timeout}s) is greater than probe "
                f"window ({probe_seconds}s)."
            )

        time.sleep(probe_seconds + 1)
        post_r = raw_client.get("/admin/session")
        assert post_r.status_code in (401, 403)


class TestCors:
    def test_preflight_allows_frontend_origin(self, base_url):
        origin = os.environ.get("TEST_FRONTEND_ORIGIN", "http://34.73.173.191")
        r = httpx.options(
            f"{base_url}/admin/accounts",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
            timeout=10.0,
        )
        assert r.status_code in (200, 204)
        assert r.headers.get("access-control-allow-origin") == origin
        assert r.headers.get("access-control-allow-credentials") == "true"

    def test_preflight_rejects_disallowed_origin(self, base_url):
        bad_origin = "https://evil.example.com"
        r = httpx.options(
            f"{base_url}/admin/accounts",
            headers={
                "Origin": bad_origin,
                "Access-Control-Request-Method": "GET",
            },
            timeout=10.0,
        )
        assert r.status_code in (200, 204, 400)
        assert r.headers.get("access-control-allow-origin") != bad_origin


class TestGenerateFlow:
    """
    Integration test: POST /generate -> poll /status -> check /results.
    Requires a running GPU backend. Skipped if no API_KEY is set
    (because that usually means we're in CI without Modal access).
    """

    @pytest.fixture(autouse=True)
    def skip_without_key(self, api_key):
        if not api_key:
            pytest.skip("API_KEY not set - skipping live generation test")

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
        assert gen_r.status_code == 200, gen_r.text

        data = gen_r.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        task_id = data["task_id"]

        # Poll for a bounded timeout (configurable via env)
        deadline = time.time() + VIDEO_FLOW_TIMEOUT_SECONDS
        final_status = None
        while time.time() < deadline:
            st_r = client.get(f"/status/{task_id}", timeout=15)
            if st_r.status_code != 200:
                pytest.fail(f"Status check failed: {st_r.status_code} {st_r.text}")
            st = st_r.json()

            assert "status" in st
            assert "progress" in st
            assert 0 <= st["progress"] <= 100

            if st["status"] in ("done", "failed"):
                final_status = st["status"]
                break

            time.sleep(POLL_INTERVAL_SECONDS)

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
        assert gen_r.status_code == 200
        task_id = gen_r.json()["task_id"]

        # Poll until done
        deadline = time.time() + IMAGE_FLOW_TIMEOUT_SECONDS
        while time.time() < deadline:
            st_r = client.get(f"/status/{task_id}")
            if st_r.status_code != 200:
                pytest.fail(f"Status check failed: {st_r.status_code} {st_r.text}")
            st = st_r.json()
            if st["status"] in ("done", "failed"):
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        del_r = client.delete(f"/gallery/{task_id}")
        assert del_r.status_code == 200
        body = del_r.json()
        assert body["deleted"] is True
        assert body["id"] == task_id

        # Should be gone now
        st_r = client.get(f"/status/{task_id}")
        assert st_r.status_code == 404

    def test_status_lifecycle_visibility(self, client):
        """Status endpoint should expose stable lifecycle states for active tasks."""
        payload = {
            "model": "pony",
            "type": "image",
            "mode": "txt2img",
            "prompt": "lifecycle visibility",
            "width": 512,
            "height": 512,
            "steps": 8,
            "seed": 2,
        }
        gen_r = client.post("/generate", json=payload)
        assert gen_r.status_code == 200, gen_r.text
        task_id = gen_r.json()["task_id"]

        allowed = {"pending", "processing", "done", "failed"}
        seen = []

        deadline = time.time() + IMAGE_FLOW_TIMEOUT_SECONDS
        final_status = None
        while time.time() < deadline:
            st_r = client.get(f"/status/{task_id}", timeout=15)
            assert st_r.status_code == 200, st_r.text
            status_value = st_r.json().get("status")
            assert status_value in allowed
            seen.append(status_value)
            if status_value in {"done", "failed"}:
                final_status = status_value
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        assert seen and seen[0] == "pending", f"Unexpected initial status sequence: {seen}"
        assert "processing" in seen, f"Expected status transition to include 'processing': {seen}"
        assert final_status in {"done", "failed"}, f"No terminal status reached: {seen}"

    def test_worker_start_timeout_transition_contract(self, client):
        """
        Optional live contract for worker-start timeout transition.
        Enable only when environment intentionally reproduces worker pickup timeout:
          TEST_FORCE_WORKER_TIMEOUT=1
        """
        if os.environ.get("TEST_FORCE_WORKER_TIMEOUT") != "1":
            pytest.skip("Set TEST_FORCE_WORKER_TIMEOUT=1 to run worker-timeout contract test")

        payload = {
            "model": "anisora",
            "type": "video",
            "mode": "t2v",
            "prompt": "force worker start timeout contract",
            "width": 512,
            "height": 512,
            "num_frames": 17,
            "fps": 8,
            "steps": 8,
            "seed": 77,
        }
        gen_r = client.post("/generate", json=payload)
        assert gen_r.status_code == 200, gen_r.text
        task_id = gen_r.json()["task_id"]

        deadline = time.time() + VIDEO_FLOW_TIMEOUT_SECONDS
        terminal = None
        terminal_payload = None
        while time.time() < deadline:
            st_r = client.get(f"/status/{task_id}", timeout=15)
            assert st_r.status_code == 200, st_r.text
            data = st_r.json()
            if data.get("status") in {"done", "failed"}:
                terminal = data.get("status")
                terminal_payload = data
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        assert terminal == "failed", f"Expected failed timeout terminal state, got: {terminal_payload}"
        detail = (terminal_payload or {}).get("stage_detail", "")
        message = (terminal_payload or {}).get("error_msg", "")
        assert ("worker_start_timeout" in detail) or ("Worker start timeout" in message)

