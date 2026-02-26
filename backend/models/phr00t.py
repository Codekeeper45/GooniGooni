"""
Phr00t WAN 2.2 Rapid video pipeline.
"""
from __future__ import annotations

import torch
from PIL import Image

from models.base import BasePipeline
from storage import preview_file_path, result_file_path


class Phr00tPipeline(BasePipeline):
    """Phr00t WAN 2.2 Rapid (single-file checkpoint)."""

    def __init__(
        self,
        hf_repo_id: str,
        hf_filename: str = "wan2.2-rapid-mega-aio-nsfw-v12.2.safetensors",
    ):
        self.hf_repo_id = hf_repo_id
        self.hf_filename = hf_filename
        self._loaded = False
        self._pipeline = None
        self._i2v_pipeline = None

    def load(self, cache_path: str) -> None:
        if self._loaded:
            return

        from huggingface_hub import hf_hub_download
        from diffusers import WanPipeline, WanImageToVideoPipeline

        ckpt_path = hf_hub_download(
            repo_id=self.hf_repo_id,
            filename=self.hf_filename,
            cache_dir=cache_path,
        )

        self._pipeline = WanPipeline.from_single_file(
            ckpt_path,
            torch_dtype=torch.bfloat16,
        )
        self._pipeline.enable_model_cpu_offload()
        if hasattr(self._pipeline, "vae"):
            self._pipeline.vae.enable_slicing()
            self._pipeline.vae.enable_tiling()

        # Reuse T2V components instead of loading the same 14B checkpoint twice.
        # from_pipe() shares transformer/text_encoder/VAE with _pipeline,
        # which already have cpu_offload hooks — do NOT call enable_model_cpu_offload() again.
        self._i2v_pipeline = WanImageToVideoPipeline.from_pipe(self._pipeline)
        if hasattr(self._i2v_pipeline, "vae") and self._i2v_pipeline.vae is not None:
            self._i2v_pipeline.vae.enable_slicing()
            self._i2v_pipeline.vae.enable_tiling()

        self._loaded = True

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
        fps = request.get("fps", 16)
        lighting_variant = request.get("lighting_variant", "low_noise")

        # Phr00t Rapid: fixed distilled settings.
        steps = 4
        cfg_scale = 1.0

        output_format = request.get("output_format", "mp4")
        out_path = result_file_path(task_id, output_format)
        prev_path = preview_file_path(task_id)

        shared = dict(
            prompt=self._apply_lighting(prompt, lighting_variant),
            negative_prompt=negative_prompt or None,
            width=width,
            height=height,
            num_frames=num_frames,
            num_inference_steps=steps,
            guidance_scale=cfg_scale,
            generator=generator,
        )

        with torch.inference_mode():
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

        self.export_video(frames, out_path, fps, output_format)

        first_frame = frames[0]
        preview_img = first_frame if isinstance(first_frame, Image.Image) else Image.fromarray(first_frame)
        self.make_preview_from_pil(preview_img, prev_path)
        return out_path, prev_path

    @staticmethod
    def _apply_lighting(prompt: str, lighting_variant: str) -> str:
        if lighting_variant == "high_noise":
            return f"{prompt}, high contrast, dramatic lighting"
        return f"{prompt}, soft lighting, low noise"
