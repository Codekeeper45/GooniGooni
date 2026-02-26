"""
Flux.1 [dev] NF4 pipeline for image generation.
"""
from __future__ import annotations

import os

import torch
from PIL import Image

from models.base import BasePipeline
from storage import preview_file_path, result_file_path


class FluxPipeline(BasePipeline):
    """Flux.1 [dev] with bitsandbytes NF4 quantization."""

    def __init__(self, hf_model_id: str):
        self.hf_model_id = hf_model_id
        self._loaded = False
        self._txt2img = None
        self._img2img = None

    def load(self, cache_path: str) -> None:
        if self._loaded:
            return

        from diffusers import FluxPipeline as FluxTxt2Img
        from diffusers import FluxImg2ImgPipeline
        from transformers import BitsAndBytesConfig
        import bitsandbytes  # noqa: F401

        nf4_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

        self._txt2img = FluxTxt2Img.from_pretrained(
            self.hf_model_id,
            cache_dir=cache_path,
            quantization_config=nf4_config,
            torch_dtype=torch.bfloat16,
            device_map="cuda",
        )
        self._img2img = FluxImg2ImgPipeline.from_pipe(self._txt2img)

        if hasattr(self._txt2img, "vae") and self._txt2img.vae is not None:
            self._txt2img.vae.enable_slicing()
            self._txt2img.vae.enable_tiling()
        if hasattr(self._img2img, "vae") and self._img2img.vae is not None:
            self._img2img.vae.enable_slicing()
            self._img2img.vae.enable_tiling()

        self._loaded = True

    def generate(self, request: dict, task_id: str, results_path: str) -> tuple[str, str]:
        if not self._loaded:
            raise RuntimeError("Pipeline not initialized. Call load() first.")

        mode = request.get("mode", "txt2img")
        seed = self.resolve_seed(request.get("seed", -1))
        generator = torch.Generator(device="cpu").manual_seed(seed)

        prompt = request["prompt"]
        negative_prompt = request.get("negative_prompt", "")
        width = request.get("width", 1024)
        height = request.get("height", 1024)
        steps = request.get("steps", 25)
        guidance_scale = request.get("guidance_scale", 3.5)
        denoising_strength = request.get("denoising_strength", 0.7)

        output_format = request.get("output_format", "png")
        if output_format not in ("png", "jpeg", "jpg"):
            output_format = "png"
        out_path = result_file_path(task_id, output_format)
        prev_path = preview_file_path(task_id)

        with torch.inference_mode():
            if mode == "txt2img":
                image = self._txt2img(
                    prompt=prompt,
                    negative_prompt=negative_prompt or None,
                    width=width,
                    height=height,
                    num_inference_steps=steps,
                    guidance_scale=guidance_scale,
                    generator=generator,
                ).images[0]

            elif mode == "img2img":
                ref_img = self.decode_image(request["reference_image"]).resize((width, height), Image.LANCZOS)
                image = self._img2img(
                    prompt=prompt,
                    negative_prompt=negative_prompt or None,
                    image=ref_img,
                    strength=denoising_strength,
                    num_inference_steps=steps,
                    guidance_scale=guidance_scale,
                    generator=generator,
                ).images[0]

            else:
                raise ValueError(f"Unsupported mode for flux: {mode}")

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        image.save(out_path)
        self.make_preview_from_pil(image, prev_path)
        return out_path, prev_path
