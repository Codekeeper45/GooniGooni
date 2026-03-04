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
    "Euler": "EulerDiscreteScheduler",
    "DPM++ 2M Karras": "DPMSolverMultistepScheduler",
    "DPM++ SDE Karras": "DPMSolverMultistepScheduler",
    "Heun": "HeunDiscreteScheduler",
    "LMS": "LMSDiscreteScheduler",
}

_DEFAULT_PONY_VAE = "madebyollin/sdxl-vae-fp16-fix"


class PonyPipeline(BasePipeline):
    """Pony Diffusion V6 XL image pipeline."""

    def __init__(self, hf_model_id: str):
        self.hf_model_id = hf_model_id
        # Allow env override but default to a stable SDXL VAE to avoid gray/NaN decodes.
        self.vae_model_id = (os.environ.get("PONY_VAE_MODEL_ID") or "").strip() or _DEFAULT_PONY_VAE
        self._loaded = False
        self._txt2img = None
        self._img2img = None

    def load(self, cache_path: str) -> None:
        if self._is_loaded_for_cache(cache_path):
            return

        from diffusers import (
            AutoencoderKL, 
            StableDiffusionXLPipeline, 
            StableDiffusionXLImg2ImgPipeline,
            DPMSolverMultistepScheduler
        )

        pipe_kwargs = dict(
            cache_dir=cache_path,
            torch_dtype=torch.bfloat16,
            use_safetensors=True,
            low_cpu_mem_usage=False,
        )

        self._txt2img = StableDiffusionXLPipeline.from_pretrained(
            self.hf_model_id,
            **pipe_kwargs,
        ).to("cuda")

        # Pony models perform much better with DPM++ 2M Karras, especially at <40 steps
        self._txt2img.scheduler = DPMSolverMultistepScheduler.from_config(
            self._txt2img.scheduler.config,
            use_karras_sigmas=True,
            algorithm_type="dpmsolver++"  # Simplified from sde-dpmsolver++
        )

        self._img2img = StableDiffusionXLImg2ImgPipeline.from_pipe(self._txt2img)

        for pipe in (self._txt2img, self._img2img):
            if hasattr(pipe, "vae") and pipe.vae is not None:
                pipe.vae.enable_slicing()
                # Force VAE to float32 to avoid colorful dot artifacts (NaNs during decode)
                pipe.vae.to(dtype=torch.float32)

        self._mark_loaded_for_cache(cache_path)

    def _apply_sampler(self, pipe, sampler_name: str) -> None:
        """Apply a specific scheduler to the pipeline."""
        from diffusers import schedulers as sched

        cls_name = _SAMPLERS.get(sampler_name, "EulerAncestralDiscreteScheduler")
        cls = getattr(sched, cls_name, sched.EulerAncestralDiscreteScheduler)
        
        kwargs = {}
        if "Karras" in sampler_name:
            kwargs["use_karras_sigmas"] = True
        
        if sampler_name == "DPM++ 2M Karras":
            kwargs["algorithm_type"] = "dpmsolver++"
        elif sampler_name == "DPM++ SDE Karras":
            kwargs["algorithm_type"] = "sde-dpmsolver++"

        pipe.scheduler = cls.from_config(pipe.scheduler.config, **kwargs)

    @staticmethod
    def _check_image_quality(image: Image.Image, caught_warnings: list = None) -> Image.Image:
        """Check the quality of a generated image and raise errors if it collapsed."""
        if image is None:
            raise RuntimeError("Pony pipeline returned empty image output.")
        
        arr = np.asarray(image)
        if not np.isfinite(arr).all():
            raise RuntimeError(
                "Pony decode produced invalid pixel values (NaN/Inf). "
                "Retry with lower resolution/steps or a different seed."
            )
        
        # Detect near-uniform gray canvas collapse before saving artifacts.
        dynamic_range = int(arr.max()) - int(arr.min())
        if dynamic_range < 4:
            raise RuntimeError(
                "Pony output collapsed to a near-uniform image. "
                "Retry with a different seed or prompt."
            )

        saw_invalid_cast_warning = False
        if caught_warnings:
             saw_invalid_cast_warning = any(
                "invalid value encountered in cast" in str(warn.message)
                for warn in caught_warnings
            )

        # RuntimeWarning alone can be noisy; fail only when it correlates with low-detail output.
        if saw_invalid_cast_warning and dynamic_range < 10:
            raise RuntimeError(
                "Pony decode produced unstable pixel values (NaN/Inf warning + low detail). "
                "Retry with lower resolution/steps or a different seed."
            )
        return image

    @staticmethod
    def _is_retryable_decode_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return (
            "invalid pixel values" in msg
            or "near-uniform image" in msg
            or "unstable pixel values" in msg
        )

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @classmethod
    def _attempt_parameters(
        cls,
        *,
        attempt: int,
        base_seed: int,
        sampler: str,
        steps: int,
        cfg_scale: float,
        denoising_strength: float,
    ) -> tuple[int, str, int, float, float]:
        """Derive per-attempt generation parameters for robust retry behavior."""
        attempt_seed = base_seed + attempt
        attempt_sampler = sampler
        attempt_steps = int(steps)
        attempt_cfg = float(cfg_scale)
        attempt_denoise = float(denoising_strength)

        if attempt == 1:
            attempt_sampler = "Euler a"
            attempt_steps = int(cls._clamp(float(attempt_steps), 28.0, 32.0))
            attempt_cfg = cls._clamp(attempt_cfg, 5.0, 6.0)
            attempt_denoise = cls._clamp(attempt_denoise, 0.45, 0.6)
        elif attempt >= 2:
            attempt_sampler = "Euler a"
            attempt_steps = 24
            attempt_cfg = 5.0
            attempt_denoise = 0.45

        return attempt_seed, attempt_sampler, attempt_steps, attempt_cfg, attempt_denoise

    @classmethod
    def _normalize_initial_resolution(cls, width: int, height: int, mode: str) -> tuple[int, int]:
        safe_side = cls._fallback_resolution(width, height)
        if width == height and 512 <= width <= 1024:
            return width, height
        if mode == "img2img" and safe_side > 768:
            safe_side = 768
        return safe_side, safe_side

    @classmethod
    def _fallback_resolution(cls, width: int, height: int) -> int:
        max_side = max(int(width), int(height))
        if max_side > 896:
            return 1024
        if max_side > 640:
            return 768
        return 512

    @classmethod
    def _attempt_resolution(
        cls,
        *,
        attempt: int,
        width: int,
        height: int,
        mode: str,
    ) -> tuple[int, int]:
        first_width, first_height = cls._normalize_initial_resolution(width, height, mode)
        if attempt <= 0:
            return first_width, first_height
        if attempt == 1:
            return 768, 768
        return 512, 512

    def generate(self, request: dict, task_id: str, results_path: str) -> tuple[str, str]:
        if not self._loaded:
            raise RuntimeError("Pipeline not initialized. Call load() first.")

        mode = request.get("mode", "txt2img")
        seed = self.resolve_seed(request.get("seed", -1))

        prompt = request["prompt"]
        negative_prompt = request.get("negative_prompt", "")
        width = request.get("width", 1024)
        height = request.get("height", 1024)
        steps = request.get("steps", 30)
        cfg_scale = request.get("cfg_scale", 6.0)
        sampler = request.get("sampler", "DPM++ 2M Karras")
        clip_skip = request.get("clip_skip", 2)
        denoising_strength = request.get("denoising_strength", 0.7)

        output_format = request.get("output_format", "png")
        if output_format not in ("png", "jpeg", "jpg"):
            output_format = "png"
        out_path = result_file_path(task_id, output_format)
        prev_path = preview_file_path(task_id)

        image = None
        last_exc: Exception | None = None
        max_attempts = 3
        for attempt in range(max_attempts):
            attempt_width, attempt_height = self._attempt_resolution(
                attempt=attempt,
                width=width,
                height=height,
                mode=mode,
            )
            attempt_seed, attempt_sampler, attempt_steps, attempt_cfg, attempt_denoise = self._attempt_parameters(
                attempt=attempt,
                base_seed=seed,
                sampler=sampler,
                steps=steps,
                cfg_scale=cfg_scale,
                denoising_strength=denoising_strength,
            )
            generator = torch.Generator(device="cuda").manual_seed(attempt_seed)
            try:
                with torch.inference_mode():
                    if mode == "txt2img":
                        self._apply_sampler(self._txt2img, attempt_sampler)
                        
                        # Generate latents
                        latents = self._txt2img(
                            prompt=prompt,
                            negative_prompt=negative_prompt or None,
                            width=attempt_width,
                            height=attempt_height,
                            num_inference_steps=attempt_steps,
                            guidance_scale=attempt_cfg,
                            generator=generator,
                            output_type="latent",
                        ).images[0]
                        
                        if not torch.isfinite(latents).all():
                            raise RuntimeError("Pony UNet produced NaNs in latents!")

                        # Manual VAE decode in float32
                        latents = latents.unsqueeze(0).to(device="cuda", dtype=torch.float32)
                        with torch.no_grad():
                            # SDXL VAE scaling factor is usually 0.13025
                            scaling_factor = getattr(self._txt2img.vae.config, "scaling_factor", 0.13025)
                            decoded = self._txt2img.vae.decode(latents / scaling_factor, return_dict=False)[0]
                            image = self._txt2img.image_processor.postprocess(decoded, output_type="pil")[0]
                        
                        image = self._check_image_quality(image)

                    elif mode == "img2img":
                        ref_img = self.decode_image(request["reference_image"]).resize(
                            (attempt_width, attempt_height),
                            Image.LANCZOS,
                        )
                        self._apply_sampler(self._img2img, attempt_sampler)
                        
                        # Generate latents from image
                        latents = self._img2img(
                            prompt=prompt,
                            negative_prompt=negative_prompt or None,
                            image=ref_img,
                            strength=attempt_denoise,
                            num_inference_steps=attempt_steps,
                            guidance_scale=attempt_cfg,
                            generator=generator,
                            output_type="latent",
                        ).images[0]

                        if not torch.isfinite(latents).all():
                            raise RuntimeError("Pony img2img UNet produced NaNs in latents!")

                        # Manual VAE decode in float32
                        latents = latents.unsqueeze(0).to(device="cuda", dtype=torch.float32)
                        with torch.no_grad():
                            scaling_factor = getattr(self._img2img.vae.config, "scaling_factor", 0.13025)
                            decoded = self._img2img.vae.decode(latents / scaling_factor, return_dict=False)[0]
                            image = self._img2img.image_processor.postprocess(decoded, output_type="pil")[0]
                        
                        image = self._check_image_quality(image)
                    else:
                        raise ValueError(f"Unsupported mode for pony: {mode}")
                request["_effective_width"] = attempt_width
                request["_effective_height"] = attempt_height
                break
            except RuntimeError as exc:
                last_exc = exc
                if self._is_retryable_decode_error(exc) and attempt < max_attempts - 1:
                    self.clear_gpu_memory(sync=False)
                    continue
                if self._is_retryable_decode_error(exc) and attempt == max_attempts - 1:
                    raise RuntimeError(
                        "Pony decode failed after 3 attempts "
                        "(including automatic safe-resolution fallback). "
                        f"Last error: {exc}. The system already retried with smaller square resolutions."
                    ) from exc
                raise

        if image is None and last_exc is not None:
            raise last_exc

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        image.save(out_path)
        self.make_preview_from_pil(image, prev_path)

        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            raise RuntimeError("Pony result file was not created.")
        if not os.path.exists(prev_path) or os.path.getsize(prev_path) == 0:
            raise RuntimeError("Pony preview file was not created.")

        return out_path, prev_path
