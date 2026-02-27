"""
Gooni Gooni Backend вЂ” Modal Application
========================================
Deploys a FastAPI server on Modal with:
  вЂў Async video generation (A10G) вЂ” anisora, phr00t
  вЂў Async image generation (A10G) вЂ” pony, flux
  вЂў REST API with API-key auth
  вЂў SQLite gallery in the results Volume

Deploy:
    modal deploy backend/app.py

Local serve (no GPU, for testing routes):
    modal serve backend/app.py
"""

import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import modal

# в”Ђв”Ђв”Ђ Modal App в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

app = modal.App("gooni-gooni-backend")

# в”Ђв”Ђв”Ђ Persistent Volumes в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

model_cache_vol = modal.Volume.from_name("model-cache", create_if_missing=True)
results_vol = modal.Volume.from_name("results", create_if_missing=True)

MODEL_CACHE_PATH = "/model-cache"
RESULTS_PATH = "/results"


def _resolve_video_gpu() -> str:
    """Return a safe GPU class for heavy Wan-based video lanes."""
    requested = os.environ.get("VIDEO_GPU", "A10G").strip() or "A10G"
    if requested.upper() == "T4":
        # T4 is insufficient for Wan 14B video generation; force a safe default.
        print("[CONFIG] VIDEO_GPU=T4 is not supported for video lanes; overriding to A10G.")
        return "A10G"
    return requested


VIDEO_GPU_CLASS = _resolve_video_gpu()
IMAGE_GPU_CLASS = os.environ.get("IMAGE_GPU", "A10G").strip() or "A10G"
VIDEO_FUNCTION_TIMEOUT = int(os.environ.get("VIDEO_TIMEOUT", "900"))
IMAGE_FUNCTION_TIMEOUT = int(os.environ.get("IMAGE_TIMEOUT", "300"))
VIDEO_FUNCTION_CPU = float(os.environ.get("VIDEO_CPU", "4"))
IMAGE_FUNCTION_CPU = float(os.environ.get("IMAGE_CPU", "4"))

# в”Ђв”Ђв”Ђ Modal Secrets в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# Create via: modal secret create gooni-api-key API_KEY=your-secret-key

api_secret = modal.Secret.from_name("gooni-api-key")
admin_secret = modal.Secret.from_name("gooni-admin")
hf_secret = modal.Secret.from_name("huggingface")
accounts_secret = modal.Secret.from_name("gooni-accounts")


# в”Ђв”Ђв”Ђ Docker Images в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

_base_pkgs = [
    "fastapi>=0.111",
    "uvicorn[standard]",
    "pydantic>=2",
    "Pillow",
    "imageio[ffmpeg]",
    "huggingface_hub",
    "httpx",
    "cryptography>=42.0.0",
    "ftfy>=6.2.0",
]

# Video generation image (A10G вЂ” 24 GB)
video_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        *_base_pkgs,
        "torch==2.4.0",
        "torchvision",
        "diffusers>=0.32",  # 0.32+ required for WanPipeline.from_single_file()
        "transformers>=4.43",
        "accelerate>=0.32",
        "sentencepiece",
        "safetensors",
        "numpy",
    )
    .env(
        {
            "HF_HOME": MODEL_CACHE_PATH,
            "TRANSFORMERS_CACHE": MODEL_CACHE_PATH,
            "PYTORCH_CUDA_ALLOC_CONF": os.environ.get(
                "PYTORCH_CUDA_ALLOC_CONF",
                "expandable_segments:True",
            ),
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES", "0"),
            "TORCH_CUDA_ARCH_LIST": os.environ.get("TORCH_CUDA_ARCH_LIST", "8.6"),
        }
    )
    .add_local_dir(str(Path(__file__).parent), remote_path="/root")  # backend/ .py files
)

# Image generation image (A10G default, includes bitsandbytes for NF4)
image_gen_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        *_base_pkgs,
        "torch==2.4.0",
        "torchvision",
        "diffusers>=0.30",
        "transformers>=4.43",
        "accelerate>=0.32",
        "bitsandbytes>=0.43",
        "safetensors",
        "numpy",
    )
    .env(
        {
            "HF_HOME": MODEL_CACHE_PATH,
            "TRANSFORMERS_CACHE": MODEL_CACHE_PATH,
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
        }
    )
    .add_local_dir(str(Path(__file__).parent), remote_path="/root")  # backend/ .py files
)

# API server image (no GPU, lightweight)
api_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(*_base_pkgs, "modal")  # modal CLI needed by deployer.py
    .add_local_dir(str(Path(__file__).parent), remote_path="/root")  # backend/ .py files
)

# в”Ђв”Ђв”Ђ Volume mounts helper в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

_volumes = {
    MODEL_CACHE_PATH: model_cache_vol,
    RESULTS_PATH: results_vol,
}

_video_pipeline_cache: dict[str, object] = {}
_image_pipeline_cache: dict[str, object] = {}
_video_lock = threading.Lock()
_image_lock = threading.Lock()
_degraded_state_lock = threading.Lock()
_degraded_active_model: Optional[str] = None


def _get_video_pipeline(model_id_key: str, *, degraded_mode: bool = False):
    """
    Return video pipeline instance.
    In degraded mode, enforce single-active heavy pipeline residency.
    """
    global _degraded_active_model
    with _video_lock:
        if degraded_mode and _degraded_active_model and _degraded_active_model != model_id_key:
            from models.base import BasePipeline

            BasePipeline.clear_all_pipelines(_video_pipeline_cache)
            _degraded_active_model = None
        if model_id_key in _video_pipeline_cache:
            if degraded_mode:
                _degraded_active_model = model_id_key
            return _video_pipeline_cache[model_id_key]

        if model_id_key == "anisora":
            from models.anisora import AnisoraPipeline
            from config import MODEL_IDS, ANISORA_SUBFOLDER

            pipeline = AnisoraPipeline(
                hf_model_id=MODEL_IDS["anisora"],
                subfolder=ANISORA_SUBFOLDER,
            )
        elif model_id_key == "phr00t":
            from models.phr00t import Phr00tPipeline
            from config import MODEL_IDS, PHR00T_FILENAME

            pipeline = Phr00tPipeline(
                hf_repo_id=MODEL_IDS["phr00t"],
                hf_filename=PHR00T_FILENAME,
            )
        else:
            raise ValueError(f"Unknown video model: {model_id_key}")

        pipeline.load(MODEL_CACHE_PATH)
        _video_pipeline_cache[model_id_key] = pipeline
        if degraded_mode:
            _degraded_active_model = model_id_key
        return pipeline


def _get_image_pipeline(model_id_key: str):
    with _image_lock:
        if model_id_key in _image_pipeline_cache:
            return _image_pipeline_cache[model_id_key]

        if model_id_key == "pony":
            from models.pony import PonyPipeline
            from config import MODEL_IDS

            pipeline = PonyPipeline(MODEL_IDS["pony"])
        elif model_id_key == "flux":
            from models.flux import FluxPipeline
            from config import MODEL_IDS

            pipeline = FluxPipeline(MODEL_IDS["flux"])
        else:
            raise ValueError(f"Unknown image model: {model_id_key}")

        pipeline.load(MODEL_CACHE_PATH)
        _image_pipeline_cache[model_id_key] = pipeline
        return pipeline

# в”Ђв”Ђв”Ђ Video Generation Function в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

def _execute_video_generation(
    request_dict: dict,
    task_id: str,
    *,
    lane_mode: str,
    fallback_reason: Optional[str] = None,
) -> dict:
    """
    Shared worker execution for heavy video pipelines.
    `lane_mode` can be `dedicated` or `degraded_shared`.
    """
    sys.path.insert(0, "/root")  # backend/ files are copied to /root

    import storage
    from models.base import BasePipeline

    def _commit_after_write() -> None:
        results_vol.commit()

    def _update_status(*args, **kwargs) -> None:
        storage.update_task_status(*args, **kwargs)
        _commit_after_write()

    def _record_event(*args, **kwargs) -> None:
        storage.record_operational_event(*args, **kwargs)
        _commit_after_write()

    def _ensure_artifacts_exist(result_path: str, preview_path: str) -> None:
        missing: list[str] = []
        for path in (result_path, preview_path):
            if not path or not os.path.exists(path):
                missing.append(path or "<empty>")
        if missing:
            raise RuntimeError(
                "Generation completed but artifact(s) missing: "
                + ", ".join(missing)
            )

    results_vol.reload()
    storage.init_db()
    _update_status(
        task_id,
        "processing",
        progress=5,
        stage="dispatch",
        stage_detail=f"video_{lane_mode}",
        lane_mode=lane_mode,
        fallback_reason=fallback_reason,
    )

    model_id_key = request_dict["model"]
    request_dict["_lane_mode"] = lane_mode

    if lane_mode == "degraded_shared":
        with _degraded_state_lock:
            cross_switch = _degraded_active_model not in (None, model_id_key)
        request_dict["_cross_model_switch"] = cross_switch
        _record_event(
            "fallback_activated",
            task_id=task_id,
            model=model_id_key,
            lane_mode=lane_mode,
            reason=fallback_reason or "capacity",
        )

    try:
        _update_status(
            task_id,
            "processing",
            progress=10,
            stage="model_resolve",
            stage_detail=f"model={model_id_key}",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )
        _record_event(
            "pipeline_resolve_started",
            task_id=task_id,
            model=model_id_key,
            lane_mode=lane_mode,
        )
        pipeline = _get_video_pipeline(
            model_id_key,
            degraded_mode=(lane_mode == "degraded_shared"),
        )
        _update_status(
            task_id,
            "processing",
            progress=35,
            stage="pipeline_materialize",
            stage_detail=f"model={model_id_key}",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )
        _record_event(
            "pipeline_ready",
            task_id=task_id,
            model=model_id_key,
            lane_mode=lane_mode,
        )

        if request_dict.get("_warmup_only"):
            _update_status(
                task_id,
                "done",
                progress=100,
                stage="completed",
                stage_detail="warmup_only",
                lane_mode=lane_mode,
                fallback_reason=fallback_reason,
            )
            _record_event(
                "lane_warmed",
                task_id=task_id,
                model=model_id_key,
                lane_mode=lane_mode,
            )
            return {"warmed": True}

        _update_status(
            task_id,
            "processing",
            progress=60,
            stage="inference",
            stage_detail=f"model={model_id_key}",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )

        result_path, preview_path = pipeline.generate(request_dict, task_id, RESULTS_PATH)
        _update_status(
            task_id,
            "processing",
            progress=90,
            stage="artifact_write",
            stage_detail="persisting_result",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )
        _ensure_artifacts_exist(result_path, preview_path)
        _update_status(
            task_id,
            "done",
            progress=100,
            result_path=result_path,
            preview_path=preview_path,
            stage="completed",
            stage_detail="ok",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )
        return {"result_path": result_path, "preview_path": preview_path}
    except Exception as exc:
        _update_status(
            task_id,
            "failed",
            error_msg=str(exc),
            stage="failed",
            stage_detail=f"{type(exc).__name__}",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )
        raise
    finally:
        allocated_gib = None
        try:
            import torch

            if torch.cuda.is_available():
                allocated_gib = torch.cuda.memory_allocated() / (1024 ** 3)
                print(f"[VRAM] After generation: {allocated_gib:.2f} GiB (lane={lane_mode}, model={model_id_key})")
        except Exception:
            pass

        BasePipeline.clear_gpu_memory(sync=False)
        _record_event(
            "memory_cleanup",
            task_id=task_id,
            model=model_id_key,
            lane_mode=lane_mode,
        )
        if allocated_gib is not None:
            _record_event(
                "memory_post_generation",
                task_id=task_id,
                model=model_id_key,
                lane_mode=lane_mode,
                value=round(allocated_gib, 3),
            )
        if lane_mode == "degraded_shared":
            storage.release_degraded_task(task_id)
            _commit_after_write()


@app.function(
    image=video_image,
    gpu=VIDEO_GPU_CLASS,
    cpu=VIDEO_FUNCTION_CPU,
    min_containers=int(os.environ.get("VIDEO_DEGRADED_MIN_CONTAINERS", "0")),
    max_containers=int(os.environ.get("VIDEO_CONCURRENCY", "1")),
    timeout=VIDEO_FUNCTION_TIMEOUT,
    volumes=_volumes,
    secrets=[api_secret, hf_secret],
)
def run_video_generation(request_dict: dict, task_id: str) -> dict:
    """Degraded shared-worker video lane."""
    return _execute_video_generation(
        request_dict=request_dict,
        task_id=task_id,
        lane_mode="degraded_shared",
        fallback_reason=request_dict.get("_fallback_reason"),
    )


@app.function(
    image=video_image,
    gpu=VIDEO_GPU_CLASS,
    cpu=VIDEO_FUNCTION_CPU,
    min_containers=int(
        os.environ.get(
            "VIDEO_ANISORA_MIN_CONTAINERS",
            os.environ.get("VIDEO_LANE_WARM_MIN_CONTAINERS", "1"),
        )
    ),
    max_containers=int(
        os.environ.get(
            "VIDEO_ANISORA_MAX_CONTAINERS",
            os.environ.get("VIDEO_LANE_WARM_MAX_CONTAINERS", "1"),
        )
    ),
    timeout=VIDEO_FUNCTION_TIMEOUT,
    volumes=_volumes,
    secrets=[api_secret, hf_secret],
)
def run_anisora_generation(request_dict: dict, task_id: str) -> dict:
    """Dedicated warm lane for AniSora."""
    request_dict["model"] = "anisora"
    return _execute_video_generation(
        request_dict=request_dict,
        task_id=task_id,
        lane_mode="dedicated",
    )


@app.function(
    image=video_image,
    gpu=VIDEO_GPU_CLASS,
    cpu=VIDEO_FUNCTION_CPU,
    min_containers=int(
        os.environ.get(
            "VIDEO_PHR00T_MIN_CONTAINERS",
            os.environ.get("VIDEO_LANE_WARM_MIN_CONTAINERS", "1"),
        )
    ),
    max_containers=int(
        os.environ.get(
            "VIDEO_PHR00T_MAX_CONTAINERS",
            os.environ.get("VIDEO_LANE_WARM_MAX_CONTAINERS", "1"),
        )
    ),
    timeout=VIDEO_FUNCTION_TIMEOUT,
    volumes=_volumes,
    secrets=[api_secret, hf_secret],
)
def run_phr00t_generation(request_dict: dict, task_id: str) -> dict:
    """Dedicated warm lane for Phr00t."""
    request_dict["model"] = "phr00t"
    return _execute_video_generation(
        request_dict=request_dict,
        task_id=task_id,
        lane_mode="dedicated",
    )


# в”Ђв”Ђв”Ђ Image Generation Functions в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

def _execute_image_generation(
    request_dict: dict,
    task_id: str,
    *,
    lane_mode: str,
    fallback_reason: Optional[str] = None,
) -> dict:
    sys.path.insert(0, "/root")

    import storage
    from models.base import BasePipeline

    def _update_status(*args, **kwargs) -> None:
        storage.update_task_status(*args, **kwargs)
        results_vol.commit()

    results_vol.reload()
    storage.init_db()
    model_id_key = request_dict["model"]

    _update_status(
        task_id,
        "processing",
        progress=5,
        stage="dispatch",
        stage_detail=f"image_{lane_mode}",
        lane_mode=lane_mode,
        fallback_reason=fallback_reason,
    )
    storage.record_operational_event(
        "pipeline_resolve_started",
        task_id=task_id,
        model=model_id_key,
        lane_mode=lane_mode,
    )
    results_vol.commit()

    try:
        _update_status(
            task_id,
            "processing",
            progress=10,
            stage="model_resolve",
            stage_detail=f"model={model_id_key}",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )
        pipeline = _get_image_pipeline(model_id_key)
        _update_status(
            task_id,
            "processing",
            progress=35,
            stage="pipeline_materialize",
            stage_detail=f"model={model_id_key}",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )
        storage.record_operational_event(
            "pipeline_ready",
            task_id=task_id,
            model=model_id_key,
            lane_mode=lane_mode,
        )
        results_vol.commit()

        if request_dict.get("_warmup_only"):
            _update_status(
                task_id,
                "done",
                progress=100,
                stage="completed",
                stage_detail="warmup_only",
                lane_mode=lane_mode,
                fallback_reason=fallback_reason,
            )
            storage.record_operational_event(
                "lane_warmed",
                task_id=task_id,
                model=model_id_key,
                lane_mode=lane_mode,
            )
            results_vol.commit()
            return {"warmed": True}

        _update_status(
            task_id,
            "processing",
            progress=60,
            stage="inference",
            stage_detail=f"model={model_id_key}",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )
        result_path, preview_path = pipeline.generate(request_dict, task_id, RESULTS_PATH)
        _update_status(
            task_id,
            "processing",
            progress=90,
            stage="artifact_write",
            stage_detail="persisting_result",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )

        if not result_path or not os.path.exists(result_path):
            raise RuntimeError(f"Image generation finished without result artifact: {result_path}")
        if not preview_path or not os.path.exists(preview_path):
            raise RuntimeError(f"Image generation finished without preview artifact: {preview_path}")

        _update_status(
            task_id,
            "done",
            progress=100,
            result_path=result_path,
            preview_path=preview_path,
            stage="completed",
            stage_detail="ok",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )
        return {"result_path": result_path, "preview_path": preview_path}
    except Exception as exc:
        _update_status(
            task_id,
            "failed",
            error_msg=str(exc),
            stage="failed",
            stage_detail=f"{type(exc).__name__}",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )
        raise
    finally:
        BasePipeline.clear_gpu_memory(sync=False)
        storage.record_operational_event(
            "memory_cleanup",
            task_id=task_id,
            model=model_id_key,
            lane_mode=lane_mode,
        )
        results_vol.commit()


@app.function(
    image=image_gen_image,
    gpu=IMAGE_GPU_CLASS,
    cpu=IMAGE_FUNCTION_CPU,
    min_containers=int(os.environ.get("IMAGE_DEGRADED_MIN_CONTAINERS", "0")),
    max_containers=int(os.environ.get("IMAGE_CONCURRENCY", "2")),
    timeout=IMAGE_FUNCTION_TIMEOUT,
    volumes=_volumes,
    secrets=[api_secret, hf_secret],
)
def run_image_generation(request_dict: dict, task_id: str) -> dict:
    """Degraded shared image lane (used as fallback)."""
    return _execute_image_generation(
        request_dict=request_dict,
        task_id=task_id,
        lane_mode="degraded_shared",
        fallback_reason=request_dict.get("_fallback_reason"),
    )


@app.function(
    image=image_gen_image,
    gpu=IMAGE_GPU_CLASS,
    cpu=IMAGE_FUNCTION_CPU,
    min_containers=int(os.environ.get("IMAGE_PONY_MIN_CONTAINERS", os.environ.get("IMAGE_LANE_WARM_MIN_CONTAINERS", "1"))),
    max_containers=int(os.environ.get("IMAGE_PONY_MAX_CONTAINERS", os.environ.get("IMAGE_LANE_WARM_MAX_CONTAINERS", "1"))),
    timeout=IMAGE_FUNCTION_TIMEOUT,
    volumes=_volumes,
    secrets=[api_secret, hf_secret],
)
def run_pony_generation(request_dict: dict, task_id: str) -> dict:
    """Dedicated warm lane for Pony."""
    request_dict["model"] = "pony"
    return _execute_image_generation(
        request_dict=request_dict,
        task_id=task_id,
        lane_mode="dedicated",
    )


@app.function(
    image=image_gen_image,
    gpu=IMAGE_GPU_CLASS,
    cpu=IMAGE_FUNCTION_CPU,
    min_containers=int(os.environ.get("IMAGE_FLUX_MIN_CONTAINERS", os.environ.get("IMAGE_LANE_WARM_MIN_CONTAINERS", "1"))),
    max_containers=int(os.environ.get("IMAGE_FLUX_MAX_CONTAINERS", os.environ.get("IMAGE_LANE_WARM_MAX_CONTAINERS", "1"))),
    timeout=IMAGE_FUNCTION_TIMEOUT,
    volumes=_volumes,
    secrets=[api_secret, hf_secret],
)
def run_flux_generation(request_dict: dict, task_id: str) -> dict:
    """Dedicated warm lane for Flux."""
    request_dict["model"] = "flux"
    return _execute_image_generation(
        request_dict=request_dict,
        task_id=task_id,
        lane_mode="dedicated",
    )


# в”Ђв”Ђв”Ђ FastAPI Server в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@app.function(
    image=api_image,
    volumes=_volumes,
    schedule=modal.Period(hours=1),
)
def cleanup_stale_tasks() -> None:
    """Periodic cleanup for tasks stuck in pending/processing states."""
    sys.path.insert(0, "/root")
    import storage

    results_vol.reload()
    storage.init_db()
    max_age_hours = int(os.environ.get("STALE_TASK_HOURS", "2"))
    updated = storage.mark_stale_tasks_failed(max_age_hours=max_age_hours)
    if updated > 0:
        results_vol.commit()


@app.function(
    image=api_image,
    volumes=_volumes,
    secrets=[api_secret],
    min_containers=int(os.environ.get("API_MIN_CONTAINERS", "1")),
    max_containers=3,
)
@modal.concurrent(max_inputs=50)
@modal.fastapi_endpoint(method="GET", label="gooni-api-health")
def health():
    """Quick health check вЂ” no auth required."""
    import sys as _sys
    if "/root" not in _sys.path:
        _sys.path.insert(0, "/root")

    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": True})


@app.function(
    image=api_image,
    volumes=_volumes,
    secrets=[api_secret, admin_secret, accounts_secret],
    min_containers=int(os.environ.get("API_MIN_CONTAINERS", "1")),
    max_containers=3,
)
@modal.concurrent(max_inputs=50)
@modal.asgi_app(label="gooni-api")
def fastapi_app():
    """
    Main ASGI application.
    The label becomes part of the public URL:
      https://<workspace>--gooni-api.modal.run

    All route logic lives in api.py (create_app).
    This function solely handles Modal bootstrapping.
    """
    import sys as _sys
    for _p in ("/root", "/root/backend"):
        if _p not in _sys.path:
            _sys.path.insert(0, _p)

    from api import create_app
    return create_app(results_vol=results_vol)

