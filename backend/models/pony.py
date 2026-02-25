"""
Pony Diffusion V6 XL pipeline – anime/hentai image generation.

Supported modes:
  • txt2img – text → image
  • img2img – reference image → image

GPU: T4 (16 GB).
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

# Map frontend sampler names → diffusers scheduler classes
_SAMPLERS = {
    "Euler a": "EulerAncestralDiscreteScheduler",
    "DPM++ 2M Karras": "DPMSolverMultistepScheduler",
    "DPM++ SDE Karras": "DPMSolverSDEScheduler",
}


class PonyPipeline(BasePipeline):
    """Pony Diffusion V6 XL – high-quality anime image generation."""

    def __init__(self, hf_model_id: str):
        self.hf_model_id = hf_model_id
        self._loaded = False

    # ─── Load ─────────────────────────────────────────────────────────────────

    def load(self, cache_path: str) -> None:
        if self._loaded:
            return

        from diffusers import StableDiffusionXLPipeline, StableDiffusionXLImg2ImgPipeline

        print(f"[pony] Loading model: {self.hf_model_id}")

        self._txt2img = StableDiffusionXLPipeline.from_pretrained(
            self.hf_model_id,
            cache_dir=cache_path,
            torch_dtype=torch.float16,
            use_safetensors=True,
        ).to("cuda")

        self._img2img = StableDiffusionXLImg2ImgPipeline.from_pipe(self._txt2img)

        self._loaded = True
        print("[pony] Model loaded ✓")

    # ─── Sampler setter ───────────────────────────────────────────────────────

    def _apply_sampler(self, pipe, sampler_name: str) -> None:
        from diffusers import schedulers as sched
        cls_name = _SAMPLERS.get(sampler_name, "EulerAncestralDiscreteScheduler")
        cls = getattr(sched, cls_name, None)
        if cls:
            # Preserve the existing config (sigma, beta, etc.)
            pipe.scheduler = cls.from_config(pipe.scheduler.config)

    # ─── Generate ─────────────────────────────────────────────────────────────

    def generate(self, request: dict, task_id: str, results_path: str) -> tuple[str, str]:
        mode = request.get("mode", "txt2img")
        seed = self.resolve_seed(request.get("seed", -1))
        generator = torch.Generator(device="cuda").manual_seed(seed)

        prompt = request["prompt"]
        negative_prompt = request.get("negative_prompt", "")
        width = request.get("width", 1024)
        height = request.get("height", 1024)
        steps = request.get("steps", 30)
        cfg_scale = request.get("cfg_scale", 6.0)
        sampler = request.get("sampler", "Euler a")
        clip_skip = request.get("clip_skip", 2)
        denoising_strength = request.get("denoising_strength", 0.7)

        output_format = request.get("output_format", "png")
        if output_format not in ("png", "jpeg", "jpg"):
            output_format = "png"
        out_path = result_file_path(task_id, output_format)
        prev_path = preview_file_path(task_id)

        if mode == "txt2img":
            self._apply_sampler(self._txt2img, sampler)
            image = self._txt2img(
                prompt=prompt,
                negative_prompt=negative_prompt or None,
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=cfg_scale,
                clip_skip=clip_skip,
                generator=generator,
            ).images[0]

        elif mode == "img2img":
            ref_img = self.decode_image(request["reference_image"]).resize((width, height), Image.LANCZOS)
            self._apply_sampler(self._img2img, sampler)
            image = self._img2img(
                prompt=prompt,
                negative_prompt=negative_prompt or None,
                image=ref_img,
                strength=denoising_strength,
                num_inference_steps=steps,
                guidance_scale=cfg_scale,
                clip_skip=clip_skip,
                generator=generator,
            ).images[0]

        else:
            raise ValueError(f"Unsupported mode for pony: {mode}")

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        image.save(out_path)

        self.make_preview_from_pil(image, prev_path)
        return out_path, prev_path
