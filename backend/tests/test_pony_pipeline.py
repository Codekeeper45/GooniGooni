"""
Unit tests for backend/models/pony.py guard logic.
"""
from __future__ import annotations

import sys
import types
import warnings
from pathlib import Path

import pytest
from PIL import Image

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

if "torch" not in sys.modules:
    torch_stub = types.ModuleType("torch")

    class _NoopCtx:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _inference_mode():
        return _NoopCtx()

    torch_stub.inference_mode = _inference_mode
    torch_stub.float16 = "float16"
    torch_stub.float32 = "float32"
    sys.modules["torch"] = torch_stub

from models.pony import PonyPipeline


class _DummyResult:
    def __init__(self, image: Image.Image):
        self.images = [image]


class _DummyPipe:
    def __init__(self, emit_invalid_cast_warning: bool):
        self.emit_invalid_cast_warning = emit_invalid_cast_warning
        self.upcast_called = False

    def upcast_vae(self):
        self.upcast_called = True

    def __call__(self, **kwargs):
        if self.emit_invalid_cast_warning:
            warnings.warn(
                "invalid value encountered in cast",
                RuntimeWarning,
                stacklevel=1,
            )
        # Non-uniform image to represent a valid decoded output.
        img = Image.new("RGB", (16, 16), (128, 128, 128))
        img.putpixel((0, 0), (96, 140, 180))
        img.putpixel((1, 1), (180, 96, 140))
        return _DummyResult(img)


class _UniformDummyPipe:
    def __call__(self, **kwargs):
        return _DummyResult(Image.new("RGB", (16, 16), (128, 128, 128)))


class _UniformWarnDummyPipe:
    def __call__(self, **kwargs):
        warnings.warn(
            "invalid value encountered in cast",
            RuntimeWarning,
            stacklevel=1,
        )
        return _DummyResult(Image.new("RGB", (16, 16), (128, 128, 128)))


def test_run_pipe_checked_returns_image_without_warning():
    pipe = _DummyPipe(emit_invalid_cast_warning=False)
    image = PonyPipeline._run_pipe_checked(pipe, prompt="ok")
    assert isinstance(image, Image.Image)


def test_run_pipe_checked_allows_invalid_cast_warning_on_non_uniform_output():
    pipe = _DummyPipe(emit_invalid_cast_warning=True)
    image = PonyPipeline._run_pipe_checked(pipe, prompt="warn")
    assert isinstance(image, Image.Image)


def test_run_pipe_checked_raises_on_uniform_collapsed_output():
    pipe = _UniformDummyPipe()
    with pytest.raises(RuntimeError) as exc:
        PonyPipeline._run_pipe_checked(pipe, prompt="flat")
    assert "near-uniform image" in str(exc.value).lower()


def test_run_pipe_checked_raises_when_warning_and_low_detail_coexist():
    pipe = _UniformWarnDummyPipe()
    with pytest.raises(RuntimeError) as exc:
        PonyPipeline._run_pipe_checked(pipe, prompt="unstable")
    message = str(exc.value).lower()
    assert ("unstable pixel values" in message) or ("near-uniform image" in message)


def test_attempt_parameters_default_attempt_keeps_original_values():
    seed, sampler, steps, cfg, denoise = PonyPipeline._attempt_parameters(
        attempt=0,
        base_seed=123,
        sampler="DPM++ 2M Karras",
        steps=40,
        cfg_scale=8.0,
        denoising_strength=0.9,
    )
    assert seed == 123
    assert sampler == "DPM++ 2M Karras"
    assert steps == 40
    assert cfg == 8.0
    assert denoise == 0.9


def test_attempt_parameters_final_attempt_uses_safe_preset():
    seed, sampler, steps, cfg, denoise = PonyPipeline._attempt_parameters(
        attempt=2,
        base_seed=123,
        sampler="DPM++ SDE Karras",
        steps=60,
        cfg_scale=10.0,
        denoising_strength=1.0,
    )
    assert seed == 125
    assert sampler == "Euler a"
    assert steps == 24
    assert cfg == 5.0
    assert denoise == 0.45


def test_attempt_resolution_normalizes_unsafe_portrait_size():
    width, height = PonyPipeline._attempt_resolution(
        attempt=0,
        width=720,
        height=1280,
        mode="txt2img",
    )
    assert (width, height) == (1024, 1024)


def test_attempt_resolution_degrades_on_retries():
    assert PonyPipeline._attempt_resolution(attempt=1, width=1024, height=1024, mode="txt2img") == (768, 768)
    assert PonyPipeline._attempt_resolution(attempt=2, width=1024, height=1024, mode="txt2img") == (512, 512)


def test_cache_guard_helpers_track_loaded_cache_path():
    pipe = PonyPipeline("hf/repo")
    assert pipe.vae_model_id == "madebyollin/sdxl-vae-fp16-fix"

    assert pipe._is_loaded_for_cache("/cache/a") is False
    pipe._mark_loaded_for_cache("/cache/a")
    assert pipe._is_loaded_for_cache("/cache/a") is True
    assert pipe._is_loaded_for_cache("/cache/b") is False
    assert getattr(pipe, "_full_load_count", 0) == 1
