"""
Index-AniSora V3.2 pipeline for anime video generation.
"""
from __future__ import annotations

import torch
from PIL import Image

from models.base import BasePipeline
from storage import preview_file_path, result_file_path


class AnisoraPipeline(BasePipeline):
    """Index-AniSora V3.2 video generation (Wan base)."""

    def __init__(self, hf_model_id: str, subfolder: str = "V3.2"):
        self.hf_model_id = hf_model_id
        self.subfolder = subfolder
        self._cache_path = ""
        self._loaded = False
        self._t2v = None
        self._i2v = None

    def load(self, cache_path: str) -> None:
        # Defer heavy loading until mode is known.
        self._cache_path = cache_path
        self._loaded = True

    def _common_kwargs(self) -> dict:
        return {
            "pretrained_model_name_or_path": self.hf_model_id,
            "subfolder": self.subfolder or None,
            "cache_dir": self._cache_path,
            "torch_dtype": torch.bfloat16,
        }

    def _ensure_t2v(self) -> None:
        if self._t2v is not None:
            return
        from diffusers import WanPipeline

        self._t2v = WanPipeline.from_pretrained(**self._common_kwargs())
        self._t2v.enable_model_cpu_offload()
        if hasattr(self._t2v, "vae"):
            self._t2v.vae.enable_slicing()
            self._t2v.vae.enable_tiling()

    def _ensure_i2v(self) -> None:
        if self._i2v is not None:
            return
        from diffusers import WanImageToVideoPipeline

        # Reuse already-loaded T2V components to avoid loading the 14B checkpoint twice.
        self._ensure_t2v()
        self._i2v = WanImageToVideoPipeline.from_pipe(self._t2v)
        # from_pipe() shares transformer/text_encoder/VAE objects with _t2v,
        # which already have cpu_offload hooks — do NOT call enable_model_cpu_offload() again.
        if hasattr(self._i2v, "vae") and self._i2v.vae is not None:
            self._i2v.vae.enable_slicing()
            self._i2v.vae.enable_tiling()

    def generate(self, request: dict, task_id: str, results_path: str) -> tuple[str, str]:
        if not self._loaded:
            raise RuntimeError("Pipeline not initialized. Call load() first.")

        mode = request.get("mode", "t2v")
        seed = self.resolve_seed(request.get("seed", -1))
        generator = torch.Generator(device="cpu").manual_seed(seed)

        prompt = request["prompt"]
        negative_prompt = request.get("negative_prompt", "")
        width = request.get("width", 720)
        height = request.get("height", 1280)
        num_frames = request.get("num_frames", 81)
        steps = request.get("steps", 8)
        fps = request.get("fps", 16)
        guidance_scale = request.get("guidance_scale", 1.0)

        output_format = request.get("output_format", "mp4")
        out_path = result_file_path(task_id, output_format)
        prev_path = preview_file_path(task_id)

        shared = dict(
            prompt=prompt,
            negative_prompt=negative_prompt or None,
            width=width,
            height=height,
            num_frames=num_frames,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            generator=generator,
        )

        with torch.inference_mode():
            if mode == "t2v":
                self._ensure_t2v()
                output = self._t2v(**shared)
                frames = output.frames[0]

            elif mode == "i2v":
                self._ensure_i2v()
                ref_img = self.decode_image(request["reference_image"])
                output = self._i2v(image=ref_img, **shared)
                frames = output.frames[0]

            elif mode == "first_last_frame":
                self._ensure_i2v()
                first = self.decode_image(request["first_frame_image"])
                last = self.decode_image(request["last_frame_image"])
                output = self._i2v(image=[first, last], **shared)
                frames = output.frames[0]

            elif mode == "arbitrary_frame":
                self._ensure_i2v()
                keyframes_raw = request.get("arbitrary_frames", [])
                keyframes_sorted = sorted(keyframes_raw, key=lambda x: x.get("frame_index", 0))
                images = [self.decode_image(kf["image"]) for kf in keyframes_sorted]
                output = self._i2v(image=images, **shared)
                frames = output.frames[0]

            else:
                raise ValueError(f"Unsupported mode for anisora: {mode}")

        self.export_video(frames, out_path, fps, output_format)

        first_frame = frames[0]
        preview_img = first_frame if isinstance(first_frame, Image.Image) else Image.fromarray(first_frame)
        self.make_preview_from_pil(preview_img, prev_path)

        return out_path, prev_path
