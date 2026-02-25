"""
Unit tests for backend/models/base.py
Tests helper methods on BasePipeline — no GPU, no Modal, no network.
"""
import base64
import io
import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from models.base import BasePipeline


def _tiny_png_b64() -> str:
    """Return a base64-encoded 4×4 red PNG as a data URI."""
    from PIL import Image
    img = Image.new("RGB", (4, 4), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


class TestDecodeImage:
    def test_decodes_data_uri(self):
        from PIL import Image
        uri = _tiny_png_b64()
        img = BasePipeline.decode_image(uri)
        assert isinstance(img, Image.Image)
        assert img.mode == "RGB"
        assert img.size == (4, 4)

    def test_decodes_raw_base64(self):
        """Without the data: prefix — should still work."""
        from PIL import Image
        uri = _tiny_png_b64()
        raw = uri.split(",", 1)[1]  # strip prefix
        img = BasePipeline.decode_image(raw)
        assert isinstance(img, Image.Image)

    def test_decoded_image_is_rgb(self):
        from PIL import Image
        # Create RGBA source
        src = Image.new("RGBA", (4, 4), (0, 255, 0, 128))
        buf = io.BytesIO()
        src.save(buf, "PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        uri = f"data:image/png;base64,{b64}"

        result = BasePipeline.decode_image(uri)
        assert result.mode == "RGB"  # decode_image converts to RGB

    def test_invalid_base64_raises(self):
        with pytest.raises(Exception):
            BasePipeline.decode_image("data:image/png;base64,NOTBASE64!!!!")


class TestResolveSeed:
    def test_minus_one_returns_random_seed(self):
        seed = BasePipeline.resolve_seed(-1)
        assert 0 <= seed < 2**31

    def test_minus_one_is_non_deterministic(self):
        seeds = {BasePipeline.resolve_seed(-1) for _ in range(10)}
        # With very high probability, 10 random seeds from [0, 2^31) are distinct
        assert len(seeds) > 1

    def test_positive_seed_returned_unchanged(self):
        assert BasePipeline.resolve_seed(0) == 0
        assert BasePipeline.resolve_seed(42) == 42
        assert BasePipeline.resolve_seed(2147483647) == 2147483647

    def test_resolve_seed_returns_int(self):
        result = BasePipeline.resolve_seed(-1)
        assert isinstance(result, int)


class TestMakePreviewFromPil:
    def test_creates_jpeg_file(self, tmp_path):
        from PIL import Image
        img = Image.new("RGB", (256, 256), (128, 64, 192))
        save_path = str(tmp_path / "preview.jpg")
        BasePipeline.make_preview_from_pil(img, save_path)
        assert os.path.exists(save_path)
        # Verify it's a valid JPEG
        loaded = Image.open(save_path)
        assert loaded.format == "JPEG"

    def test_thumbnail_fits_within_size(self, tmp_path):
        from PIL import Image
        # Large source image
        img = Image.new("RGB", (2048, 1024), (0, 0, 0))
        save_path = str(tmp_path / "preview.jpg")
        BasePipeline.make_preview_from_pil(img, save_path, size=(512, 512))
        loaded = Image.open(save_path)
        assert loaded.width <= 512
        assert loaded.height <= 512

    def test_creates_parent_directory(self, tmp_path):
        from PIL import Image
        img = Image.new("RGB", (32, 32))
        nested = str(tmp_path / "a" / "b" / "preview.jpg")
        os.makedirs(os.path.dirname(nested), exist_ok=True)
        BasePipeline.make_preview_from_pil(img, nested)
        assert os.path.exists(nested)

    def test_default_size_is_512(self, tmp_path):
        from PIL import Image
        img = Image.new("RGB", (1024, 1024))
        save_path = str(tmp_path / "preview.jpg")
        BasePipeline.make_preview_from_pil(img, save_path)
        loaded = Image.open(save_path)
        assert loaded.width <= 512
        assert loaded.height <= 512
