"""Persistent Pony Diffusion V6 XL txt2img/img2img pipeline."""
from __future__ import annotations

import os

import torch
from PIL import Image

from models.base import BasePipeline
from storage import preview_file_path, result_file_path


class PonyPipeline(BasePipeline):
    def __init__(self, hf_model_id: str):
        self.hf_model_id = hf_model_id
        self._loaded = False

    def load(self, cache_path: str) -> None:
        if self._loaded:
            return

        from diffusers import (
            StableDiffusionXLImg2ImgPipeline,
            StableDiffusionXLPipeline,
        )

        torch.backends.cuda.matmul.allow_tf32 = True
        print(f"[pony] loading {self.hf_model_id}")
        self._txt2img = StableDiffusionXLPipeline.from_pretrained(
            self.hf_model_id,
            cache_dir=cache_path,
            torch_dtype=torch.float16,
            use_safetensors=True,
        )
        self._txt2img.enable_vae_slicing()
        self._txt2img.to("cuda")
        self._img2img = StableDiffusionXLImg2ImgPipeline.from_pipe(self._txt2img)
        self._loaded = True
        print("[pony] ready")

    @staticmethod
    def _apply_sampler(pipe, sampler_name: str) -> None:
        from diffusers import (
            DPMSolverMultistepScheduler,
            DPMSolverSDEScheduler,
            EulerAncestralDiscreteScheduler,
        )

        config = pipe.scheduler.config
        if sampler_name == "DPM++ 2M Karras":
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(
                config,
                algorithm_type="dpmsolver++",
                use_karras_sigmas=True,
            )
        elif sampler_name == "DPM++ SDE Karras":
            pipe.scheduler = DPMSolverSDEScheduler.from_config(
                config,
                use_karras_sigmas=True,
            )
        else:
            pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(config)

    @torch.inference_mode()
    def generate(
        self,
        request: dict,
        task_id: str,
        results_path: str,
    ) -> tuple[str, str, int]:
        del results_path  # Paths are constructed centrally by storage.py.
        seed = self.resolve_seed(request["seed"])
        generator = torch.Generator(device="cuda").manual_seed(seed)
        mode = request["mode"]
        sampler = request["sampler"]

        common = {
            "prompt": request["prompt"],
            "negative_prompt": request["negative_prompt"] or None,
            "num_inference_steps": request["steps"],
            "guidance_scale": request["cfg_scale"],
            "clip_skip": request["clip_skip"],
            "generator": generator,
        }

        if mode == "txt2img":
            self._apply_sampler(self._txt2img, sampler)
            image = self._txt2img(
                **common,
                width=request["width"],
                height=request["height"],
            ).images[0]
        elif mode == "img2img":
            self._apply_sampler(self._img2img, sampler)
            reference = self.decode_image(request["reference_image"])
            reference = reference.resize(
                (request["width"], request["height"]),
                Image.Resampling.LANCZOS,
            )
            image = self._img2img(
                **common,
                image=reference,
                strength=request["denoising_strength"],
            ).images[0]
        else:
            raise ValueError(f"Unsupported mode: {mode}")

        output_path = result_file_path(task_id, request["output_format"])
        preview_path = preview_file_path(task_id)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if request["output_format"] == "jpeg":
            image.save(output_path, "JPEG", quality=95, optimize=True)
        else:
            image.save(output_path, "PNG", optimize=True)
        self.make_preview_from_pil(image, preview_path)
        return output_path, preview_path, seed
