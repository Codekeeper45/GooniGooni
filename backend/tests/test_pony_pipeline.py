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
        return _DummyResult(Image.new("RGB", (16, 16), (128, 128, 128)))


def test_run_pipe_checked_returns_image_without_warning():
    pipe = _DummyPipe(emit_invalid_cast_warning=False)
    image = PonyPipeline._run_pipe_checked(pipe, prompt="ok")
    assert isinstance(image, Image.Image)
    assert pipe.upcast_called is True


def test_run_pipe_checked_raises_on_invalid_cast_warning():
    pipe = _DummyPipe(emit_invalid_cast_warning=True)
    with pytest.raises(RuntimeError) as exc:
        PonyPipeline._run_pipe_checked(pipe, prompt="bad")
    assert "invalid pixel values" in str(exc.value).lower()
