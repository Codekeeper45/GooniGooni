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

        saw_invalid_cast_warning = any(
            "invalid value encountered in cast" in str(warn.message)
            for warn in caught
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
        dynamic_range = int(arr.max()) - int(arr.min())
        if dynamic_range < 4:
            raise RuntimeError(
                "Pony output collapsed to a near-uniform image. "
                "Retry with a different seed or prompt."
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
        max_attempts: int,
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

        # On the final attempt use a safer preset to reduce SDXL decode instability.
        if attempt == max_attempts - 1:
            attempt_sampler = "Euler a"
            attempt_steps = int(cls._clamp(float(attempt_steps), 24.0, 30.0))
            attempt_cfg = cls._clamp(attempt_cfg, 4.5, 6.5)
            attempt_denoise = cls._clamp(attempt_denoise, 0.45, 0.7)

        return attempt_seed, attempt_sampler, attempt_steps, attempt_cfg, attempt_denoise

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
        sampler = request.get("sampler", "Euler a")
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
            attempt_seed, attempt_sampler, attempt_steps, attempt_cfg, attempt_denoise = self._attempt_parameters(
                attempt=attempt,
                max_attempts=max_attempts,
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
                        image = self._run_pipe_checked(
                            self._txt2img,
                            prompt=prompt,
                            negative_prompt=negative_prompt or None,
                            width=width,
                            height=height,
                            num_inference_steps=attempt_steps,
                            guidance_scale=attempt_cfg,
                            clip_skip=clip_skip,
                            generator=generator,
                        )

                    elif mode == "img2img":
                        ref_img = self.decode_image(request["reference_image"]).resize((width, height), Image.LANCZOS)
                        self._apply_sampler(self._img2img, attempt_sampler)
                        image = self._run_pipe_checked(
                            self._img2img,
                            prompt=prompt,
                            negative_prompt=negative_prompt or None,
                            image=ref_img,
                            strength=attempt_denoise,
                            num_inference_steps=attempt_steps,
                            guidance_scale=attempt_cfg,
                            clip_skip=clip_skip,
                            generator=generator,
                        )
                    else:
                        raise ValueError(f"Unsupported mode for pony: {mode}")
                break
            except RuntimeError as exc:
                last_exc = exc
                if self._is_retryable_decode_error(exc) and attempt < max_attempts - 1:
                    self.clear_gpu_memory(sync=False)
                    continue
                if self._is_retryable_decode_error(exc) and attempt == max_attempts - 1:
                    raise RuntimeError(
                        "Pony decode failed after 3 attempts "
                        "(including safe preset fallback). "
                        f"Last error: {exc}"
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
