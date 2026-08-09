"""Live Modal smoke tests.

Run with:
  pytest backend/tests/test_api.py --base-url URL --api-key KEY
"""
import time

import httpx
import pytest


def test_health(base_url):
    response = httpx.get(f"{base_url}/health")
    assert response.status_code == 200
    assert response.json()["model"] == "pony"


def test_protected_endpoints_reject_missing_key(base_url):
    assert httpx.get(f"{base_url}/models").status_code == 403
    assert httpx.get(f"{base_url}/gallery").status_code == 403


def test_only_pony_model_is_exposed(client):
    response = client.get("/models")
    assert response.status_code == 200
    models = response.json()["models"]
    assert [model["id"] for model in models] == ["pony"]
    assert models[0]["modes"] == ["txt2img", "img2img"]


def test_removed_video_payload_is_rejected(client):
    response = client.post(
        "/generate",
        json={
            "model": "anisora",
            "type": "video",
            "mode": "t2v",
            "prompt": "test",
        },
    )
    assert response.status_code == 422


@pytest.mark.live_gpu
def test_real_txt2img_completes_and_downloads(client, api_key):
    if not api_key:
        pytest.skip("Live GPU generation requires an API key")
    response = client.post(
        "/generate",
        json={
            "model": "pony",
            "type": "image",
            "mode": "txt2img",
            "prompt": "score_9, simple blue circle on white background",
            "negative_prompt": "text, watermark",
            "width": 512,
            "height": 512,
            "steps": 10,
            "cfg_scale": 6,
            "sampler": "Euler a",
            "clip_skip": 2,
            "denoising_strength": 0.7,
            "seed": 42,
            "output_format": "png",
            "reference_image": None,
        },
    )
    assert response.status_code == 202, response.text
    task_id = response.json()["task_id"]
    deadline = time.time() + 900
    status = None
    while time.time() < deadline:
        status = client.get(f"/status/{task_id}").json()
        if status["status"] in {"done", "failed", "cancelled"}:
            break
        time.sleep(5)
    assert status is not None
    assert status["status"] == "done", status
    result = client.get(status["result_url"])
    assert result.status_code == 200
    assert result.headers["content-type"].startswith("image/")
    assert len(result.content) > 1000
