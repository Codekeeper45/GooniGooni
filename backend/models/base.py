"""
Abstract base class for all inference pipelines.
"""
from __future__ import annotations

import abc
import base64
import binascii
import io
import random

from PIL import Image, ImageOps

from config import PONY_CONTRACT


class BasePipeline(abc.ABC):
    """
    Every model pipeline implements this interface.
    Subclasses are instantiated once per Modal container and kept alive.
    """

    model_id: str  # HuggingFace repo ID or local path

    @abc.abstractmethod
    def load(self, cache_path: str) -> None:
        """
        Download / load model weights.
        `cache_path` is the mount path of the model-cache Volume.
        """
        ...

    @abc.abstractmethod
    def generate(self, request: dict, task_id: str, results_path: str) -> tuple[str, str, int]:
        """
        Execute inference.

        Args:
            request:      The GenerateRequest serialized to dict.
            task_id:      Unique ID for this generation job.
            results_path: Root path of the results Volume.

        Returns:
            (result_file_path, preview_file_path, resolved_seed).
        """
        ...

    # ─── Shared helpers ───────────────────────────────────────────────────────

    @staticmethod
    def decode_image(data_uri: str) -> Image.Image:
        """Decode a base64 data URI into a PIL Image."""
        if not data_uri:
            raise ValueError("Reference image is empty")
        if "," in data_uri:
            data_uri = data_uri.split(",", 1)[1]
        try:
            raw = base64.b64decode(data_uri, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Reference image is not valid base64") from exc
        max_bytes = PONY_CONTRACT["limits"]["reference_max_bytes"]
        if len(raw) > max_bytes:
            raise ValueError("Reference image exceeds the 10 MB limit")
        try:
            with Image.open(io.BytesIO(raw)) as source:
                source.verify()
            with Image.open(io.BytesIO(raw)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
        except Exception as exc:
            raise ValueError("Reference image cannot be decoded") from exc
        if image.width * image.height > 25_000_000:
            raise ValueError("Reference image dimensions are too large")
        return image

    @staticmethod
    def resolve_seed(seed: int) -> int:
        """Return a concrete seed (-1 → random)."""
        return random.randint(0, 2_147_483_647) if seed == -1 else seed

    @staticmethod
    def make_preview_from_pil(image: Image.Image, save_path: str, size: tuple[int, int] = (512, 512)) -> None:
        """Save a thumbnail JPEG from a PIL Image."""
        thumb = image.copy()
        thumb.thumbnail(size, Image.LANCZOS)
        thumb.save(save_path, "JPEG", quality=85)
