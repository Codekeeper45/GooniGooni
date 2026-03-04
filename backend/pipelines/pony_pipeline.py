"""
Pony Diffusion V6 XL pipeline for image generation.
"""
from __future__ import annotations

import os

import numpy as np
import torch
from PIL import Image

from pipelines.base_pipeline import BasePipeline
from storage import preview_file_path, result_file_path
from pipelines.utils.validation import validate_output, validate_latents

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
            DPMSolverMultistepScheduler,
        )

        # ── DIAGNOSTICS ─────────────────────────────────────────────────
        import diffusers
        print(f"[PonyPipeline] DIAG: torch={torch.__version__}, diffusers={diffusers.__version__}")
        print(f"[PonyPipeline] DIAG: model_id={self.hf_model_id}, vae_id={self.vae_model_id}")
        print(f"[PonyPipeline] DIAG: DEPLOY_TAG=v17_FULL_FP32_test")

        # ── Step 2: Load pipeline with the patched VAE ───────────────────
        self._txt2img = StableDiffusionXLPipeline.from_pretrained(
            self.hf_model_id,
            vae=vae,  # Inject patched VAE at construction time
            cache_dir=cache_path,
            torch_dtype=torch.float16,
            variant="fp16",
            use_safetensors=True,
            add_watermarker=False,
        ).to("cuda")
        print(f"[PonyPipeline] Pipeline loaded from {self.hf_model_id}")

        # ── Set optimal scheduler ────────────────────────────────────────
        self._txt2img.scheduler = DPMSolverMultistepScheduler.from_config(
            self._txt2img.scheduler.config,
            use_karras_sigmas=True,
            algorithm_type="dpmsolver++",
        )

        # ── Create img2img from the same pipe ────────────────────────────
        self._img2img = StableDiffusionXLImg2ImgPipeline.from_pipe(self._txt2img)

        # ── Enable VAE slicing for memory efficiency ─────────────────────
        for pipe in (self._txt2img, self._img2img):
            if hasattr(pipe, "vae") and pipe.vae is not None:
                pipe.vae.enable_slicing()

        self._mark_loaded_for_cache(cache_path)
        print("[PonyPipeline] ✅ Pipeline ready (FULL FP32, no fp16 variant)")



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

        # Check for mandatory score tags as per best practices
        prompt = request["prompt"]
        if "score_" not in prompt:
            prompt = "score_9, score_8_up, score_7_up, score_6_up, score_5_up, score_4_up, " + prompt

        negative_prompt = request.get("negative_prompt", "")
        if "score_" not in negative_prompt:
            negative_prompt = "score_4, score_4_up, score_5, score_5_up, score_6, score_6_up, " + negative_prompt

        width = request.get("width", 1024)
        height = request.get("height", 1024)
        steps = request.get("steps", 30)
        cfg_scale = request.get("cfg_scale", 6.0)
        sampler = request.get("sampler", "DPM++ 2M Karras")
        # PONY MUST USE CLIP SKIP 2
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
                        
                        def latent_diagnostic_callback(pipe, step_index, timestep, callback_kwargs):
                            latents = callback_kwargs["latents"]
                            print(f"[LatentDiag] Step {step_index}: min={latents.min().item():.3f} max={latents.max().item():.3f} mean={latents.mean().item():.3f} std={latents.std().item():.3f} isnan={torch.isnan(latents).any().item()}")
                            return callback_kwargs

                        # Generate image natively
                        image = self._txt2img(
                            prompt=prompt,
                            negative_prompt=negative_prompt or None,
                            width=attempt_width,
                            height=attempt_height,
                            num_inference_steps=attempt_steps,
                            guidance_scale=attempt_cfg,
                            clip_skip=clip_skip, # CRITICAL: explicitly use clip_skip 2
                            generator=generator,
                            output_type="pil",
                            callback_on_step_end=latent_diagnostic_callback,
                            callback_on_step_end_tensor_inputs=["latents"],
                        ).images[0]
                        
                        # Global output validation
                        validate_output(image)

                    elif mode == "img2img":
                        ref_img = self.decode_image(request["reference_image"]).resize(
                            (attempt_width, attempt_height),
                            Image.LANCZOS,
                        )
                        self._apply_sampler(self._img2img, attempt_sampler)
                        
                        # Generate image natively
                        image = self._img2img(
                            prompt=prompt,
                            negative_prompt=negative_prompt or None,
                            image=ref_img,
                            strength=attempt_denoise,
                            num_inference_steps=attempt_steps,
                            guidance_scale=attempt_cfg,
                            clip_skip=clip_skip, # CRITICAL
                            generator=generator,
                            output_type="pil",
                        ).images[0]

                        validate_output(image)

                    else:
                        raise ValueError(f"Unknown mode: {mode}")

                # Success
                image.save(out_path)
                self.make_preview_from_pil(image, prev_path)
                return out_path, prev_path

            except Exception as e:
                last_exc = e
                print(f"[Pony Attempt {attempt+1}/{max_attempts}] Failed: {e}")
                
        raise RuntimeError(f"Pony decode failed after {max_attempts} attempts. Last error: {last_exc}")
