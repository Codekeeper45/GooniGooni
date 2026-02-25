"""
Phr00t WAN 2.2 Rapid-AllInOne NSFW pipeline – realistic video generation.

This model is distributed as a single safetensors checkpoint (AllInOne format),
NOT as a Diffusers-compatible folder. It includes the transformer, text encoder,
VAE, and CLIP all bundled in one file.

Loading strategy:
  • Use `hf_hub_download` to fetch the specific safetensors file.
  • Use `WanPipeline.from_single_file()` (supported since diffusers >= 0.32).

Supported modes:
  • t2v              – text → video
  • i2v              – reference image → video
  • first_last_frame – first + last frames → video

Fixed parameters (as designed by Phr00t):
  • steps     = 4   (non-negotiable for the Rapid distillation)
  • cfg_scale = 1.0 (flow-matching — no CFG needed)

GPU: A10G (24 GB).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
from models.base import BasePipeline
from storage import result_file_path, preview_file_path


class Phr00tPipeline(BasePipeline):
    """Phr00t WAN 2.2 Rapid – rapid realistic video generation (single-file)."""

    def __init__(
        self,
        hf_repo_id: str,
        hf_filename: str = "wan2.2-rapid-mega-aio-nsfw-v12.2.safetensors",
    ):
        self.hf_repo_id = hf_repo_id
        self.hf_filename = hf_filename
        self._pipeline = None
        self._i2v_pipeline = None
        self._loaded = False

    # ─── Load ─────────────────────────────────────────────────────────────────

    def load(self, cache_path: str) -> None:
        if self._loaded:
            return

        from huggingface_hub import hf_hub_download
        from diffusers import WanPipeline, WanImageToVideoPipeline

        print(f"[phr00t] Downloading checkpoint: {self.hf_repo_id}/{self.hf_filename}")

        # Download the single .safetensors file into the model-cache volume
        ckpt_path = hf_hub_download(
            repo_id=self.hf_repo_id,
            filename=self.hf_filename,
            cache_dir=cache_path,
        )

        print(f"[phr00t] Loading T2V pipeline from: {ckpt_path}")
        self._pipeline = WanPipeline.from_single_file(
            ckpt_path,
            torch_dtype=torch.bfloat16,
        )
        self._pipeline.enable_model_cpu_offload()
        if hasattr(self._pipeline, "vae"):
            self._pipeline.vae.enable_slicing()

        print(f"[phr00t] Loading I2V pipeline from same checkpoint")
        self._i2v_pipeline = WanImageToVideoPipeline.from_single_file(
            ckpt_path,
            torch_dtype=torch.bfloat16,
        )
        self._i2v_pipeline.enable_model_cpu_offload()
        if hasattr(self._i2v_pipeline, "vae"):
            self._i2v_pipeline.vae.enable_slicing()

        self._loaded = True
        print("[phr00t] Model loaded ✓")

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

        # Phr00t Rapid uses distillation: FIXED 4 steps + cfg 1.0
        steps = 4
        cfg_scale = 1.0

        # Lighting variant: "high_noise" or "low_noise"
        lighting_variant = request.get("lighting_variant", "low_noise")

        output_format = request.get("output_format", "mp4")
        out_path = result_file_path(task_id, output_format)
        prev_path = preview_file_path(task_id)

        # Build prompt with lighting variant suffix (as Phr00t recommends)
        full_prompt = self._apply_lighting(prompt, lighting_variant)
        negative_prompt_full = negative_prompt or None

        # ── Common kwargs ──────────────────────────────────────────────────────
        shared = dict(
            prompt=full_prompt,
            negative_prompt=negative_prompt_full,
            width=width,
            height=height,
            num_frames=num_frames,
            num_inference_steps=steps,
            guidance_scale=cfg_scale,
            generator=generator,
        )

        if mode == "t2v":
            output = self._pipeline(**shared)
            frames = output.frames[0]

        elif mode == "i2v":
            ref_img = self.decode_image(request["reference_image"])
            output = self._i2v_pipeline(image=ref_img, **shared)
            frames = output.frames[0]

        elif mode == "first_last_frame":
            first = self.decode_image(request["first_frame_image"])
            last = self.decode_image(request["last_frame_image"])
            output = self._i2v_pipeline(image=[first, last], **shared)
            frames = output.frames[0]

        else:
            raise ValueError(f"Unsupported mode for phr00t: {mode}")

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
    def _apply_lighting(prompt: str, lighting_variant: str) -> str:
        """
        Phr00t's AllInOne model supports lighting via prompt tags.
        high_noise → 'noisy' lighting feel (dramatic)
        low_noise  → 'clean' lighting feel (soft, default)
        """
        if lighting_variant == "high_noise":
            return f"{prompt}, high contrast, dramatic lighting"
        else:
            return f"{prompt}, soft lighting, low noise"

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
