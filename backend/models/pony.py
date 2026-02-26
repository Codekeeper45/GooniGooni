"""
Pony Diffusion V6 XL pipeline for image generation.
"""
from __future__ import annotations

import os
import warnings

import numpy as np
import torch
from PIL import Image

from models.base import BasePipeline
from storage import preview_file_path, result_file_path

_SAMPLERS = {
    "Euler a": "EulerAncestralDiscreteScheduler",
    "DPM++ 2M Karras": "DPMSolverMultistepScheduler",
    "DPM++ SDE Karras": "DPMSolverSDEScheduler",
}


class PonyPipeline(BasePipeline):
    """Pony Diffusion V6 XL image pipeline."""

    def __init__(self, hf_model_id: str):
        self.hf_model_id = hf_model_id
        # Optional override for experimentation; by default use model-native VAE.
        self.vae_model_id = (os.environ.get("PONY_VAE_MODEL_ID") or "").strip() or None
        self._loaded = False
        self._txt2img = None
        self._img2img = None

    def load(self, cache_path: str) -> None:
        if self._loaded:
            return

        from diffusers import AutoencoderKL, StableDiffusionXLPipeline, StableDiffusionXLImg2ImgPipeline

        pipe_kwargs = dict(
            cache_dir=cache_path,
            torch_dtype=torch.float16,
            use_safetensors=True,
            low_cpu_mem_usage=False,
        )
        if self.vae_model_id:
            pipe_kwargs["vae"] = AutoencoderKL.from_pretrained(
                self.vae_model_id,
                cache_dir=cache_path,
                torch_dtype=torch.float16,
            )

        self._txt2img = StableDiffusionXLPipeline.from_pretrained(
            self.hf_model_id,
            **pipe_kwargs,
        )
        # Fix for NaN fp16 VAE outputs (SDXL VAE bug on float16)
        if hasattr(self._txt2img, "vae") and self._txt2img.vae is not None:
            self._txt2img.vae = self._txt2img.vae.to(dtype=torch.float32)

        self._txt2img.enable_model_cpu_offload()
        self._img2img = StableDiffusionXLImg2ImgPipeline.from_pipe(self._txt2img)

        for pipe in (self._txt2img, self._img2img):
            if hasattr(pipe, "vae") and pipe.vae is not None:
                pipe.vae.enable_slicing()
                pipe.vae.enable_tiling()

        self._loaded = True

    def _apply_sampler(self, pipe, sampler_name: str) -> None:
        from diffusers import schedulers as sched

        cls_name = _SAMPLERS.get(sampler_name, "EulerAncestralDiscreteScheduler")
        cls = getattr(sched, cls_name, None)
        if cls:
            pipe.scheduler = cls.from_config(pipe.scheduler.config)

    @staticmethod
    def _run_pipe_checked(pipe, **kwargs) -> Image.Image:
        # SDXL VAE decode is more stable in fp32.
        if hasattr(pipe, "vae") and pipe.vae is not None:
            pipe.vae.to(dtype=torch.float32)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", RuntimeWarning)
            image = pipe(**kwargs).images[0]

        for warn in caught:
            message = str(warn.message)
            if "invalid value encountered in cast" in message:
                raise RuntimeError(
                    "Pony decode produced invalid pixel values (NaN/Inf). "
                    "Retry with lower resolution/steps or a different seed."
                )

        if image is None:
            raise RuntimeError("Pony pipeline returned empty image output.")
        arr = np.asarray(image)
        if not np.isfinite(arr).all():
            raise RuntimeError(
                "Pony decode produced invalid pixel values (NaN/Inf). "
                "Retry with lower resolution/steps or a different seed."
            )
        # Detect near-uniform gray canvas collapse before saving artifacts.
        if (arr.max() - arr.min()) < 4:
            raise RuntimeError(
                "Pony output collapsed to a near-uniform image. "
                "Retry with a different seed or prompt."
            )
        return image

    def generate(self, request: dict, task_id: str, results_path: str) -> tuple[str, str]:
        if not self._loaded:
            raise RuntimeError("Pipeline not initialized. Call load() first.")

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

        with torch.inference_mode():
            if mode == "txt2img":
                self._apply_sampler(self._txt2img, sampler)
                image = self._run_pipe_checked(
                    self._txt2img,
                    prompt=prompt,
                    negative_prompt=negative_prompt or None,
                    width=width,
                    height=height,
                    num_inference_steps=steps,
                    guidance_scale=cfg_scale,
                    clip_skip=clip_skip,
                    generator=generator,
                )

            elif mode == "img2img":
                ref_img = self.decode_image(request["reference_image"]).resize((width, height), Image.LANCZOS)
                self._apply_sampler(self._img2img, sampler)
                image = self._run_pipe_checked(
                    self._img2img,
                    prompt=prompt,
                    negative_prompt=negative_prompt or None,
                    image=ref_img,
                    strength=denoising_strength,
                    num_inference_steps=steps,
                    guidance_scale=cfg_scale,
                    clip_skip=clip_skip,
                    generator=generator,
                )

            else:
                raise ValueError(f"Unsupported mode for pony: {mode}")

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        image.save(out_path)
        self.make_preview_from_pil(image, prev_path)

        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            raise RuntimeError("Pony result file was not created.")
        if not os.path.exists(prev_path) or os.path.getsize(prev_path) == 0:
            raise RuntimeError("Pony preview file was not created.")

        return out_path, prev_path
