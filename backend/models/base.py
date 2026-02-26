"""
Abstract base class for all inference pipelines.
"""
from __future__ import annotations

import abc
import base64
import io
import os
import random
from typing import Optional

from PIL import Image


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
    def generate(self, request: dict, task_id: str, results_path: str) -> tuple[str, str]:
        """
        Execute inference.

        Args:
            request:      The GenerateRequest serialized to dict.
            task_id:      Unique ID for this generation job.
            results_path: Root path of the results Volume.

        Returns:
            (result_file_path, preview_file_path) – absolute paths inside the volume.
        """
        ...

    # ─── Shared helpers ───────────────────────────────────────────────────────

    @staticmethod
    def decode_image(data_uri: str) -> Image.Image:
        """Decode a base64 data URI into a PIL Image."""
        if "," in data_uri:
            data_uri = data_uri.split(",", 1)[1]
        raw = base64.b64decode(data_uri)
        return Image.open(io.BytesIO(raw)).convert("RGB")

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

    @staticmethod
    def make_preview_from_video(video_path: str, preview_path: str, size: tuple[int, int] = (512, 512)) -> None:
        """Extract the first frame of an MP4 and save as JPEG thumbnail."""
        import imageio
        reader = imageio.get_reader(video_path, "ffmpeg")
        frame = reader.get_data(0)  # numpy array (H, W, C)
        reader.close()
        img = Image.fromarray(frame)
        BasePipeline.make_preview_from_pil(img, preview_path, size)

    @staticmethod
    def export_video(frames: list, out_path: str, fps: int, output_format: str) -> None:
        """Write frames to video without duplicating full frame list in memory."""
        import imageio
        import numpy as np

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        codec = "libx264" if output_format == "mp4" else "vp9"
        with imageio.get_writer(out_path, fps=fps, codec=codec, quality=8) as writer:
            for frame in frames:
                writer.append_data(np.array(frame) if isinstance(frame, Image.Image) else frame)
