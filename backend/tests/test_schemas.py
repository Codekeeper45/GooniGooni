"""Strict Pony-only request/response contract tests."""
import base64
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from config import PONY_CONTRACT
from schemas import GenerateRequest, StatusResponse, TaskStatus


def make_request(**overrides):
    payload = {"prompt": "score_9, detailed character"}
    payload.update(overrides)
    return GenerateRequest(**payload)


def test_defaults_come_from_shared_contract():
    request = make_request()
    defaults = PONY_CONTRACT["defaults"]
    assert request.model == "pony"
    assert request.type == "image"
    assert request.mode == PONY_CONTRACT["model"]["default_mode"]
    assert request.width == defaults["width"]
    assert request.height == defaults["height"]
    assert request.steps == defaults["steps"]
    assert request.cfg_scale == defaults["cfg_scale"]
    assert request.sampler == defaults["sampler"]
    assert request.clip_skip == defaults["clip_skip"]
    assert request.denoising_strength == defaults["denoising_strength"]
    assert request.seed == defaults["seed"]
    assert request.output_format == defaults["output_format"]


@pytest.mark.parametrize("field,value", [
    ("model", "flux"),
    ("type", "video"),
    ("mode", "t2v"),
    ("sampler", "made up"),
    ("output_format", "webm"),
])
def test_removed_capabilities_are_rejected(field, value):
    with pytest.raises(ValidationError):
        make_request(**{field: value})


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError) as error:
        make_request(motion_score=3.0)
    assert "Extra inputs are not permitted" in str(error.value)


def test_img2img_requires_reference():
    with pytest.raises(ValidationError):
        make_request(mode="img2img")


def test_txt2img_rejects_reference():
    with pytest.raises(ValidationError):
        make_request(reference_image="data:image/png;base64,AAAA")


def test_img2img_accepts_reference():
    image = base64.b64encode(b"test").decode()
    request = make_request(
        mode="img2img",
        reference_image=f"data:image/png;base64,{image}",
    )
    assert request.reference_image is not None


@pytest.mark.parametrize("dimension", [511, 513, 1544])
def test_dimensions_are_bounded_and_divisible_by_eight(dimension):
    with pytest.raises(ValidationError):
        make_request(width=dimension)


def test_total_pixel_limit_prevents_t4_oom_configuration():
    with pytest.raises(ValidationError):
        make_request(width=1536, height=1536)


def test_text_is_trimmed():
    request = make_request(prompt="  hello  ", negative_prompt="  bad  ")
    assert request.prompt == "hello"
    assert request.negative_prompt == "bad"


def test_status_has_no_fake_progress_field():
    response = StatusResponse(
        task_id="fc-123",
        status=TaskStatus.processing,
        message="Queued or generating on GPU",
    )
    assert "progress" not in response.model_dump()
