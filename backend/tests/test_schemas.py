"""
Unit tests for backend/schemas.py.
"""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from schemas import GenerateRequest, GenerateResponse, StatusResponse, TaskStatus

SAMPLE_IMAGE = "data:image/png;base64,AAAA"


def make_req(**kwargs):
    """Build a minimal valid payload and merge kwargs."""
    base = {
        "model": "pony",
        "type": "image",
        "mode": "txt2img",
        "prompt": "test prompt",
    }
    base.update(kwargs)

    if base["mode"] in {"img2img", "i2v"}:
        base.setdefault("reference_image", SAMPLE_IMAGE)
    if base["mode"] == "first_last_frame":
        base.setdefault("first_frame_image", SAMPLE_IMAGE)
        base.setdefault("last_frame_image", SAMPLE_IMAGE)
    if base["mode"] == "arbitrary_frame":
        base.setdefault(
            "arbitrary_frames",
            [{"frame_index": 0, "image": SAMPLE_IMAGE, "strength": 0.85}],
        )

    return GenerateRequest(**base)


class TestValidRequests:
    def test_pony_txt2img(self):
        req = make_req(model="pony", type="image", mode="txt2img")
        assert req.model.value == "pony"
        assert req.mode == "txt2img"

    def test_pony_img2img(self):
        req = make_req(model="pony", type="image", mode="img2img")
        assert req.mode == "img2img"

    def test_flux_txt2img(self):
        req = make_req(model="flux", type="image", mode="txt2img")
        assert req.model.value == "flux"

    def test_flux_img2img(self):
        req = make_req(model="flux", type="image", mode="img2img")
        assert req.mode == "img2img"

    def test_anisora_t2v(self):
        req = make_req(model="anisora", type="video", mode="t2v")
        assert req.type.value == "video"

    def test_anisora_i2v(self):
        make_req(model="anisora", type="video", mode="i2v")

    def test_anisora_first_last_frame(self):
        make_req(model="anisora", type="video", mode="first_last_frame")

    def test_anisora_arbitrary_frame(self):
        make_req(model="anisora", type="video", mode="arbitrary_frame")

    def test_phr00t_t2v(self):
        make_req(model="phr00t", type="video", mode="t2v")

    def test_phr00t_i2v(self):
        make_req(model="phr00t", type="video", mode="i2v")

    def test_phr00t_first_last_frame(self):
        make_req(model="phr00t", type="video", mode="first_last_frame")


class TestModeValidation:
    def test_phr00t_arbitrary_frame_rejected(self):
        with pytest.raises(ValidationError):
            make_req(model="phr00t", type="video", mode="arbitrary_frame")

    def test_pony_t2v_rejected(self):
        with pytest.raises(ValidationError):
            make_req(model="pony", type="image", mode="t2v")

    def test_anisora_txt2img_rejected(self):
        with pytest.raises(ValidationError):
            make_req(model="anisora", type="video", mode="txt2img")

    def test_unknown_model_rejected(self):
        with pytest.raises(ValidationError):
            make_req(model="foobar", type="image", mode="txt2img")

    def test_unknown_type_rejected(self):
        with pytest.raises(ValidationError):
            make_req(model="pony", type="audio", mode="txt2img")


class TestFieldConstraints:
    def test_prompt_required(self):
        with pytest.raises(ValidationError):
            GenerateRequest(model="pony", type="image", mode="txt2img", prompt="")

    def test_prompt_max_length(self):
        with pytest.raises(ValidationError):
            make_req(prompt="x" * 2001)

    def test_negative_prompt_default_empty_string(self):
        req = make_req()
        assert req.negative_prompt == ""

    def test_negative_prompt_max_length(self):
        with pytest.raises(ValidationError):
            make_req(negative_prompt="x" * 1001)

    def test_width_minimum(self):
        with pytest.raises(ValidationError):
            make_req(width=100)

    def test_height_minimum(self):
        with pytest.raises(ValidationError):
            make_req(height=100)

    def test_width_maximum(self):
        with pytest.raises(ValidationError):
            make_req(width=4096)

    def test_seed_minus_one_allowed(self):
        req = make_req(seed=-1)
        assert req.seed == -1

    def test_seed_too_low_rejected(self):
        with pytest.raises(ValidationError):
            make_req(seed=-2)

    def test_seed_max_allowed(self):
        req = make_req(seed=2147483647)
        assert req.seed == 2147483647

    def test_default_output_format_mp4_for_video(self):
        req = make_req(model="anisora", type="video", mode="t2v")
        assert req.output_format == "mp4"


class TestResponseSchemas:
    def test_generate_response(self):
        resp = GenerateResponse(task_id="abc-123", status=TaskStatus.pending)
        assert resp.task_id == "abc-123"
        assert resp.status == TaskStatus.pending

    def test_status_response_pending(self):
        resp = StatusResponse(
            task_id="abc-123",
            status=TaskStatus.pending,
            progress=0,
        )
        assert resp.progress == 0
        assert resp.error is None

    def test_status_response_done(self):
        resp = StatusResponse(
            task_id="abc-123",
            status=TaskStatus.done,
            progress=100,
            result_url="https://example.com/results/abc-123",
            preview_url="https://example.com/preview/abc-123",
        )
        assert resp.result_url is not None

    def test_task_status_enum_values(self):
        assert TaskStatus.pending.value == "pending"
        assert TaskStatus.processing.value == "processing"
        assert TaskStatus.done.value == "done"
        assert TaskStatus.failed.value == "failed"
