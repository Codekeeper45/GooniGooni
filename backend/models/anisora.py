"""
Index-AniSora V3.2 pipeline for anime video generation.

AniSora V3.2 is based on Wan 2.2 architecture (NOT CogVideoX).
Weights are in the "V3.2" subfolder of IndexTeam/Index-anisora.

Supported modes:
  • t2v              – text → video
  • i2v              – reference image → video
  • first_last_frame – first + last frames → video (interpolation)
  • arbitrary_frame  – multi-keyframe video with VACE guidance

GPU: A10G (24 GB). Uses enable_model_cpu_offload() for VRAM headroom.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import torch
from PIL import Image

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from models.base import BasePipeline
from storage import result_file_path, preview_file_path


class AnisoraPipeline(BasePipeline):
    """Index-AniSora V3.2 – anime video generation (Wan2.2 base)."""

    def __init__(self, hf_model_id: str, subfolder: str = "V3.2"):
        self.hf_model_id = hf_model_id
        self.subfolder = subfolder
        self.pipeline = None
        self._loaded = False

    # ─── Load ─────────────────────────────────────────────────────────────────

    def load(self, cache_path: str) -> None:
        if self._loaded:
            return

        # AniSora V3.2 is Wan2.2-based. Different pipeline classes are used
        # for T2V (text-to-video) and I2V (image-to-video) modes.
        from diffusers import WanPipeline, WanImageToVideoPipeline

        print(f"[anisora] Loading model: {self.hf_model_id} (subfolder={self.subfolder})")

        common_kwargs = dict(
            pretrained_model_name_or_path=self.hf_model_id,
            subfolder=self.subfolder,
            cache_dir=cache_path,
            torch_dtype=torch.bfloat16,
        )

        # Text-to-video pipeline
        self._t2v = WanPipeline.from_pretrained(**common_kwargs)
        self._t2v.enable_model_cpu_offload()
        if hasattr(self._t2v, "vae"):
            self._t2v.vae.enable_slicing()
            self._t2v.vae.enable_tiling()

        # Image-to-video pipeline (reuses weights from _t2v where possible)
        self._i2v = WanImageToVideoPipeline.from_pretrained(**common_kwargs)
        self._i2v.enable_model_cpu_offload()
        if hasattr(self._i2v, "vae"):
            self._i2v.vae.enable_slicing()
            self._i2v.vae.enable_tiling()

        self._loaded = True
        print("[anisora] Model loaded ✓")

    # ─── Generate ─────────────────────────────────────────────────────────────

    def generate(self, request: dict, task_id: str, results_path: str) -> tuple[str, str]:
        mode = request.get("mode", "t2v")
        seed = self.resolve_seed(request.get("seed", -1))
        generator = torch.Generator(device="cpu").manual_seed(seed)

        prompt = request["prompt"]
        negative_prompt = request.get("negative_prompt", "")
        width = request.get("width", 720)
        height = request.get("height", 1280)
        num_frames = request.get("num_frames", 81)
        fps = request.get("fps", 16)
        # AniSora is a flow-matching model — guidance_scale ~ 1.0 works well
        guidance_scale = request.get("guidance_scale", 1.0)

        output_format = request.get("output_format", "mp4")
        out_path = result_file_path(task_id, output_format)
        prev_path = preview_file_path(task_id)

        # ── Common kwargs ──────────────────────────────────────────────────────
        shared = dict(
            prompt=prompt,
            negative_prompt=negative_prompt or None,
            width=width,
            height=height,
            num_frames=num_frames,
            guidance_scale=guidance_scale,
            generator=generator,
        )

        if mode == "t2v":
            output = self._t2v(**shared)
            frames = output.frames[0]

        elif mode == "i2v":
            ref_img = self.decode_image(request["reference_image"])
            output = self._i2v(image=ref_img, **shared)
            frames = output.frames[0]

        elif mode == "first_last_frame":
            # Wan2.2 I2V: pass image list [first, last] for interpolation
            first = self.decode_image(request["first_frame_image"])
            last = self.decode_image(request["last_frame_image"])
            output = self._i2v(image=[first, last], **shared)
            frames = output.frames[0]

        elif mode == "arbitrary_frame":
            # Multi-keyframe: sort by frame_index, pass as image list
            keyframes_raw = request.get("arbitrary_frames", [])
            keyframes_sorted = sorted(
                keyframes_raw, key=lambda x: x.get("frame_index", 0)
            )
            images = [self.decode_image(kf["image"]) for kf in keyframes_sorted]
            output = self._i2v(image=images, **shared)
            frames = output.frames[0]

        else:
            raise ValueError(f"Unsupported mode for anisora: {mode}")

        # Save video
        self._export_video(frames, out_path, fps, output_format)

        # Save preview (first frame)
        first_frame = frames[0]
        preview_img = (
            first_frame
            if isinstance(first_frame, Image.Image)
            else Image.fromarray(first_frame)
        )
        self.make_preview_from_pil(preview_img, prev_path)

        return out_path, prev_path

    # ─── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _export_video(
        frames: list,
        out_path: str,
        fps: int,
        output_format: str,
    ) -> None:
        import imageio
        import numpy as np

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        codec = "libx264" if output_format == "mp4" else "vp9"

        np_frames = [
            np.array(f) if isinstance(f, Image.Image) else f
            for f in frames
        ]

        with imageio.get_writer(out_path, fps=fps, codec=codec, quality=8) as writer:
            for frame in np_frames:
                writer.append_data(frame)
