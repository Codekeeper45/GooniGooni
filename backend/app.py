"""
Gooni Gooni Backend — Modal Application
========================================
Deploys a FastAPI server on Modal with:
  • Async video generation (A10G) — anisora, phr00t
  • Async image generation (A10G) — pony, flux
  • REST API with API-key auth
  • SQLite gallery in the results Volume

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

# ─── Modal App ────────────────────────────────────────────────────────────────

app = modal.App("gooni-gooni-backend")

# ─── Persistent Volumes ───────────────────────────────────────────────────────

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

# ─── Modal Secrets ────────────────────────────────────────────────────────────
# Create via: modal secret create gooni-api-key API_KEY=your-secret-key

api_secret = modal.Secret.from_name("gooni-api-key")
admin_secret = modal.Secret.from_name("gooni-admin")
hf_secret = modal.Secret.from_name("huggingface")
accounts_secret = modal.Secret.from_name("gooni-accounts")


# ─── Docker Images ────────────────────────────────────────────────────────────

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

# Video generation image (A10G — 24 GB)
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

# ─── Volume mounts helper ─────────────────────────────────────────────────────

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

# ─── Video Generation Function ────────────────────────────────────────────────

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
            stage="loading_pipeline",
            stage_detail=f"model={model_id_key}",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )
        pipeline = _get_video_pipeline(
            model_id_key,
            degraded_mode=(lane_mode == "degraded_shared"),
        )
        _update_status(
            task_id,
            "processing",
            progress=25,
            stage="inference",
            stage_detail=f"model={model_id_key}",
            lane_mode=lane_mode,
            fallback_reason=fallback_reason,
        )

        result_path, preview_path = pipeline.generate(request_dict, task_id, RESULTS_PATH)
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
    min_containers=int(os.environ.get("VIDEO_DEGRADED_MIN_CONTAINERS", "0")),
    max_containers=int(os.environ.get("VIDEO_CONCURRENCY", "1")),
    timeout=900,
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
    timeout=900,
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
    timeout=900,
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


# ─── Image Generation Function ────────────────────────────────────────────────

@app.function(
    image=image_gen_image,
    gpu=os.environ.get("IMAGE_GPU", "A10G"),
    min_containers=int(os.environ.get("IMAGE_MIN_CONTAINERS", "1")),
    max_containers=int(os.environ.get("IMAGE_CONCURRENCY", "2")),
    timeout=300,
    volumes=_volumes,
    secrets=[api_secret, hf_secret],
)
def run_image_generation(request_dict: dict, task_id: str) -> dict:
    """
    Modal function that runs on A10G by default.
    Supports pony (SDXL) and flux (NF4) models.
    """
    sys.path.insert(0, "/root")

    import storage
    results_vol.reload()
    storage.init_db()
    storage.update_task_status(task_id, "processing", progress=5)
    results_vol.commit()

    model_id_key = request_dict["model"]

    try:
        storage.update_task_status(task_id, "processing", progress=10)
        results_vol.commit()
        pipeline = _get_image_pipeline(model_id_key)
        storage.update_task_status(task_id, "processing", progress=20)
        results_vol.commit()

        result_path, preview_path = pipeline.generate(request_dict, task_id, RESULTS_PATH)
        storage.update_task_status(
            task_id, "done", progress=100,
            result_path=result_path,
            preview_path=preview_path,
        )
        results_vol.commit()
        return {"result_path": result_path, "preview_path": preview_path}
    except Exception as exc:
        storage.update_task_status(task_id, "failed", error_msg=str(exc))
        results_vol.commit()
        raise


# ─── FastAPI Server ───────────────────────────────────────────────────────────

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
    """Quick health check — no auth required."""
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
    Main ASGI application — all routes live here.
    The label becomes part of the public URL:
      https://<workspace>--gooni-api.modal.run
    """
    import sys as _sys
    for _p in ("/root", "/root/backend"):
        if _p not in _sys.path:
            _sys.path.insert(0, _p)

    import asyncio
    import time

    from fastapi import Depends, FastAPI, HTTPException, Query, Request, status, Body
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse, Response

    import storage
    import accounts as acc_store
    from auth import verify_api_key, verify_generation_session, GENERATION_SESSION_COOKIE
    from config import (
        MODELS_SCHEMA,
        DEFAULT_PAGE_SIZE,
        DB_PATH,
        DEGRADED_QUEUE_MAX_DEPTH,
        DEGRADED_QUEUE_MAX_WAIT_SECONDS,
        DEGRADED_QUEUE_OVERLOAD_CODE,
    )
    from router import router as account_router, NoReadyAccountError, MAX_FALLBACKS
    from deployer import deploy_account_async, deploy_all_accounts
    from schemas import (
        DeleteResponse,
        GalleryResponse,
        GenerateRequest,
        GenerateResponse,
        GenerationSessionStateResponse,
        AdminSessionStateResponse,
        HealthResponse,
        ModelsResponse,
        StatusResponse,
        TaskStatus,
        AccountResponse,
        ErrorResponse,
    )

    # ── Init DB on cold start ─────────────────────────────────────────────────
    storage.init_db()
    acc_store.init_accounts_table()

    enable_docs = (os.environ.get("ENABLE_DOCS", "0").strip().lower() in {"1", "true", "yes", "on"})
    if not (os.environ.get("PUBLIC_BASE_URL", "").strip()):
        print(
            "[CONFIG] PUBLIC_BASE_URL is not set; /status links may be null until caller applies request-base fallback."
        )

    api = FastAPI(
        title="Gooni Gooni Backend",
        description="AI content generation API (images & videos)",
        version="1.0.0",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
    )

    env_origins = [
        origin.strip()
        for origin in os.environ.get("FRONTEND_ORIGINS", "").split(",")
        if origin.strip()
    ]
    default_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://34.73.173.191",
        "https://34.73.173.191",
    ]
    allowed_origins = sorted(set(default_origins + env_origins))

    api.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        # Keep explicit allowlist + regex fallback for same hosts with explicit ports.
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|34\.73\.173\.191)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    generation_ttl_seconds = int(os.environ.get("GENERATION_SESSION_TTL_SECONDS", str(24 * 3600)))
    admin_idle_timeout_seconds = int(
        os.environ.get("ADMIN_SESSION_IDLE_TIMEOUT_SECONDS", str(12 * 3600))
    )
    # Cookie security attributes are fixed by project constitution.
    session_cookie_secure = True
    session_cookie_samesite = "none"

    def _set_session_cookie(response: Response, key: str, value: str, max_age: int) -> None:
        response.set_cookie(
            key=key,
            value=value,
            max_age=max_age,
            httponly=True,
            secure=session_cookie_secure,
            samesite=session_cookie_samesite,
            path="/",
        )

    def _delete_session_cookie(response: Response, key: str) -> None:
        response.delete_cookie(
            key=key,
            httponly=True,
            secure=session_cookie_secure,
            samesite=session_cookie_samesite,
            path="/",
        )

    def _error_payload(code: str, detail: str, user_action: str) -> dict:
        return ErrorResponse(code=code, detail=detail, user_action=user_action).model_dump()

    _ERROR_CODE_BY_STATUS = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        410: "resource_gone",
        422: "validation_error",
        429: "rate_limited",
        500: "internal_error",
        502: "upstream_error",
        503: "service_unavailable",
    }

    _USER_ACTION_BY_STATUS = {
        400: "Check request parameters and retry.",
        401: "Re-authenticate and retry.",
        403: "Check credentials and retry.",
        404: "Verify the identifier and retry.",
        409: "Retry the operation.",
        410: "Regenerate the asset and retry.",
        422: "Fix request fields and retry.",
        429: "Retry after a short delay.",
        500: "Retry later.",
        502: "Retry shortly.",
        503: "Retry later.",
    }

    def _as_api_error(status_code: int, detail: object) -> dict:
        if isinstance(detail, dict):
            code = str(detail.get("code") or _ERROR_CODE_BY_STATUS.get(status_code, "request_failed"))
            message = str(detail.get("detail") or "Request failed.")
            action = str(detail.get("user_action") or _USER_ACTION_BY_STATUS.get(status_code, "Retry later."))
            payload = _error_payload(code=code, detail=message, user_action=action)
            metadata = detail.get("metadata")
            if isinstance(metadata, dict):
                payload["metadata"] = metadata
            return payload
        if isinstance(detail, str):
            return _error_payload(
                code=_ERROR_CODE_BY_STATUS.get(status_code, "request_failed"),
                detail=detail,
                user_action=_USER_ACTION_BY_STATUS.get(status_code, "Retry later."),
            )
        return _error_payload(
            code=_ERROR_CODE_BY_STATUS.get(status_code, "request_failed"),
            detail="Request failed.",
            user_action=_USER_ACTION_BY_STATUS.get(status_code, "Retry later."),
        )

    @api.exception_handler(HTTPException)
    async def _http_exception_handler(_: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_as_api_error(exc.status_code, exc.detail),
        )

    @api.exception_handler(RequestValidationError)
    async def _validation_exception_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                **_error_payload(
                    code="validation_error",
                    detail="Request validation failed.",
                    user_action="Fix request fields and retry.",
                ),
                "metadata": {"errors": exc.errors()},
            },
        )

    def _normalize_request_dict(req: GenerateRequest) -> dict:
        req_dict = req.model_dump()
        req_dict["model"] = req.model.value
        req_dict["type"] = req.type.value
        model_key = req_dict["model"]
        if model_key == "anisora" and req_dict.get("steps") is None:
            req_dict["steps"] = 8
        if model_key == "phr00t":
            if req_dict.get("steps") is None:
                req_dict["steps"] = 4
            if req_dict.get("cfg_scale") is None and req_dict.get("guidance_scale") is not None:
                req_dict["cfg_scale"] = req_dict["guidance_scale"]
            if req_dict.get("cfg_scale") is None:
                req_dict["cfg_scale"] = 1.0
        return req_dict

    def _fallback_reason_from_error(exc: Exception) -> str:
        text = str(exc).lower()
        if "quota" in text:
            return "quota"
        if "manual" in text:
            return "manual"
        return "capacity"

    async def _admit_degraded_queue(task_id: str, model_key: str) -> tuple[bool, float, int]:
        started = time.monotonic()
        while True:
            admitted, depth = storage.try_admit_degraded_task(
                task_id,
                max_depth=DEGRADED_QUEUE_MAX_DEPTH,
            )
            waited_seconds = time.monotonic() - started
            if admitted:
                storage.record_operational_event(
                    "queue_admitted",
                    task_id=task_id,
                    model=model_key,
                    lane_mode="degraded_shared",
                    value=depth,
                )
                return True, waited_seconds, depth
            if waited_seconds >= DEGRADED_QUEUE_MAX_WAIT_SECONDS:
                storage.record_operational_event(
                    "queue_timeout",
                    task_id=task_id,
                    model=model_key,
                    lane_mode="degraded_shared",
                    value=round(waited_seconds, 3),
                )
                return False, waited_seconds, depth
            await asyncio.sleep(0.5)

    async def _spawn_local_generation(
        req: GenerateRequest,
        *,
        force_degraded_reason: Optional[str] = None,
    ) -> GenerateResponse:
        import random

        params = req.model_dump(
            exclude={
                "prompt",
                "negative_prompt",
                "model",
                "type",
                "mode",
                "width",
                "height",
                "seed",
                "reference_image",
                "first_frame_image",
                "last_frame_image",
                "arbitrary_frames",
            },
        )
        model_key = req.model.value
        lane_mode = "dedicated" if req.type.value == "video" else None
        resolved_seed = req.seed if req.seed != -1 else random.randint(0, 2_147_483_647)
        task_id = storage.create_task(
            model=model_key,
            gen_type=req.type.value,
            mode=req.mode,
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            parameters=params,
            width=req.width,
            height=req.height,
            seed=resolved_seed,
            lane_mode=lane_mode,
            fallback_reason=force_degraded_reason,
        )
        req_dict = _normalize_request_dict(req)
        req_dict["seed"] = resolved_seed

        if req.type.value != "video":
            try:
                run_image_generation.spawn(req_dict, task_id)
            except Exception as exc:
                storage.update_task_status(
                    task_id,
                    "failed",
                    error_msg=f"Spawn failed: {exc}",
                    stage="failed",
                    stage_detail="spawn_failed",
                )
                results_vol.commit()
                raise HTTPException(
                    status_code=503,
                    detail=_error_payload(
                        code="enqueue_failed",
                        detail="Failed to enqueue image generation task.",
                        user_action="Retry later.",
                    ),
                )
            storage.update_task_status(
                task_id,
                "pending",
                progress=0,
                stage="queued",
                stage_detail="image_lane",
            )
            results_vol.commit()
            return GenerateResponse(task_id=task_id, status=TaskStatus.pending)

        fallback_reason = force_degraded_reason
        if fallback_reason is None:
            try:
                if model_key == "anisora":
                    run_anisora_generation.spawn(req_dict, task_id)
                elif model_key == "phr00t":
                    run_phr00t_generation.spawn(req_dict, task_id)
                else:
                    raise ValueError(f"Unsupported video model: {model_key}")
                storage.record_operational_event(
                    "warm_lane_ready",
                    task_id=task_id,
                    model=model_key,
                    lane_mode="dedicated",
                )
                storage.update_task_status(
                    task_id,
                    "pending",
                    progress=0,
                    stage="queued",
                    stage_detail="dedicated_lane",
                    lane_mode="dedicated",
                )
                results_vol.commit()
                return GenerateResponse(task_id=task_id, status=TaskStatus.pending)
            except Exception as exc:
                fallback_reason = _fallback_reason_from_error(exc)
                storage.record_operational_event(
                    "fallback_activated",
                    task_id=task_id,
                    model=model_key,
                    lane_mode="degraded_shared",
                    reason=fallback_reason,
                )

        admitted, waited, depth = await _admit_degraded_queue(task_id, model_key)
        if not admitted:
            storage.update_task_status(
                task_id,
                "failed",
                error_msg=DEGRADED_QUEUE_OVERLOAD_CODE,
                stage="rejected",
                stage_detail=DEGRADED_QUEUE_OVERLOAD_CODE,
                lane_mode="degraded_shared",
                fallback_reason=fallback_reason,
            )
            storage.record_operational_event(
                "queue_overloaded",
                task_id=task_id,
                model=model_key,
                lane_mode="degraded_shared",
                value=depth,
                reason=fallback_reason,
            )
            results_vol.commit()
            raise HTTPException(
                status_code=503,
                detail={
                    **_error_payload(
                        code=DEGRADED_QUEUE_OVERLOAD_CODE,
                        detail=(
                            f"Generation queue is overloaded (depth={depth}, "
                            f"max_depth={DEGRADED_QUEUE_MAX_DEPTH}, max_wait={DEGRADED_QUEUE_MAX_WAIT_SECONDS}s)."
                        ),
                        user_action="Retry later.",
                    ),
                    "metadata": {
                        "depth": depth,
                        "max_depth": DEGRADED_QUEUE_MAX_DEPTH,
                        "max_wait_seconds": DEGRADED_QUEUE_MAX_WAIT_SECONDS,
                    },
                },
            )

        req_dict["_fallback_reason"] = fallback_reason or "capacity"
        req_dict["_degraded_wait_seconds"] = round(waited, 3)
        req_dict["_degraded_queue_depth"] = depth

        try:
            run_video_generation.spawn(req_dict, task_id)
        except Exception as exc:
            storage.release_degraded_task(task_id)
            storage.update_task_status(
                task_id,
                "failed",
                error_msg=f"Spawn failed: {exc}",
                stage="failed",
                stage_detail="degraded_spawn_failed",
                lane_mode="degraded_shared",
                fallback_reason=fallback_reason,
            )
            results_vol.commit()
            raise HTTPException(
                status_code=503,
                detail=_error_payload(
                    code="enqueue_failed",
                    detail="Failed to enqueue degraded video generation task.",
                    user_action="Retry later.",
                ),
            )

        storage.update_task_status(
            task_id,
            "pending",
            progress=0,
            stage="queued",
            stage_detail=f"degraded_wait={round(waited, 3)}s",
            lane_mode="degraded_shared",
            fallback_reason=fallback_reason,
        )
        storage.record_operational_event(
            "queue_depth",
            task_id=task_id,
            model=model_key,
            lane_mode="degraded_shared",
            value=depth,
            reason=fallback_reason,
        )
        results_vol.commit()
        return GenerateResponse(task_id=task_id, status=TaskStatus.pending)

    # ── GET /health ────────────────────────────────────────────────────────────
    @api.get("/health", response_model=HealthResponse, tags=["Info"])
    async def health_check():
        return HealthResponse()

    @api.post(
        "/auth/session",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["Auth"],
    )
    async def create_generation_session(response: Response, request: Request):
        results_vol.reload()
        client_ip = request.client.host if request.client else "unknown"
        token, expires_at = storage.create_generation_session(
            ttl_seconds=generation_ttl_seconds,
            client_context=client_ip,
        )
        results_vol.commit()
        _set_session_cookie(
            response=response,
            key=GENERATION_SESSION_COOKIE,
            value=token,
            max_age=generation_ttl_seconds,
        )
        return None

    @api.get(
        "/auth/session",
        response_model=GenerationSessionStateResponse,
        tags=["Auth"],
    )
    async def get_generation_session_state(request: Request):
        token = request.cookies.get(GENERATION_SESSION_COOKIE, "")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "generation_session_missing",
                    "detail": "Generation session is missing.",
                    "user_action": "Create a new session and retry.",
                },
            )
        results_vol.reload()
        active, reason, expires_at = storage.validate_generation_session(token)
        if not active:
            code = "generation_session_expired" if reason == "expired" else "generation_session_invalid"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": code,
                    "detail": "Generation session is invalid or expired.",
                    "user_action": "Create a new session and retry.",
                },
            )
        return GenerationSessionStateResponse(valid=True, active=True, expires_at=expires_at)

    @api.delete(
        "/auth/session",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["Auth"],
    )
    async def delete_generation_session(response: Response, request: Request):
        token = request.cookies.get(GENERATION_SESSION_COOKIE, "")
        if token:
            results_vol.reload()
            storage.revoke_generation_session(token)
            results_vol.commit()
        _delete_session_cookie(response, GENERATION_SESSION_COOKIE)
        return None

    # ── GET /models ────────────────────────────────────────────────────────────
    @api.get("/models", response_model=ModelsResponse, tags=["Info"])
    async def list_models(_: str = Depends(verify_api_key)):
        return ModelsResponse(models=MODELS_SCHEMA)

    # ── POST /generate_direct ──────────────────────────────────────────────────
    @api.post(
        "/generate_direct",
        response_model=GenerateResponse,
        status_code=status.HTTP_200_OK,
        tags=["Generation"],
    )
    async def generate_direct(
        req: GenerateRequest,
        _: str = Depends(verify_api_key),
    ):
        """Internal endpoint for isolated Modal account execution."""
        results_vol.reload()
        return await _spawn_local_generation(req)

    # ── POST /generate ─────────────────────────────────────────────────────────
    @api.post(
        "/generate",
        response_model=GenerateResponse,
        status_code=status.HTTP_200_OK,
        tags=["Generation"],
    )
    async def generate(
        req: GenerateRequest,
        _: str = Depends(verify_generation_session),
    ):
        results_vol.reload()
        tried_accounts: list[str] = []
        last_error = ""

        import httpx
        api_key_env = os.environ.get("API_KEY", "")
        headers = {"X-API-Key": api_key_env} if api_key_env else {}
        req_payload = _normalize_request_dict(req)

        for attempt in range(MAX_FALLBACKS + 1):
            try:
                if attempt == 0:
                    account = account_router.pick()
                else:
                    account = account_router.pick_with_fallback(tried=tried_accounts)

                tried_accounts.append(account["id"])
                workspace = account.get("workspace")
                if not workspace:
                    raise Exception("Account has no workspace configured.")

                remote_url = f"https://{workspace}--gooni-api.modal.run/generate_direct"

                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=5.0)
                ) as client:
                    resp = await client.post(remote_url, json=req_payload, headers=headers)
                    if resp.status_code == 422:
                        payload = {}
                        try:
                            payload = resp.json()
                        except Exception:
                            payload = {}
                        if isinstance(payload, dict) and {"code", "detail", "user_action"}.issubset(payload):
                            raise HTTPException(status_code=422, detail=payload)
                        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
                        if isinstance(detail, dict) and {"code", "detail", "user_action"}.issubset(detail):
                            raise HTTPException(status_code=422, detail=detail)
                        raise HTTPException(
                            status_code=422,
                            detail=_error_payload(
                                code="validation_error",
                                detail="Validation failed.",
                                user_action="Fix request fields and retry.",
                            ),
                        )
                    if resp.status_code >= 400:
                        raise Exception(f"remote_{resp.status_code}:{resp.text[:200]}")
                    data = resp.json()
                    remote_task_id = data["task_id"]

                account_router.mark_success(account["id"])
                
                # Format task ID to encode the remote workspace
                return GenerateResponse(
                    task_id=f"{workspace}::{remote_task_id}",
                    status=TaskStatus.pending
                )

            except NoReadyAccountError:
                break
            except HTTPException:
                raise
            except Exception as exc:
                last_error = str(exc)
                if tried_accounts:
                    account_router.mark_failed(tried_accounts[-1], last_error)

        if last_error:
            storage.record_operational_event(
                "fallback_activated",
                model=req.model.value,
                lane_mode="degraded_shared" if req.type.value == "video" else None,
                reason=_fallback_reason_from_error(Exception(last_error)),
            )
        return await _spawn_local_generation(req)

    # ── GET /status/{task_id} ──────────────────────────────────────────────────
    @api.get(
        "/status/{task_id}",
        response_model=StatusResponse,
        tags=["Generation"],
    )
    async def get_status(
        task_id: str,
        _: str = Depends(verify_generation_session),
    ):
        if "::" in task_id:
            workspace, remote_task_id = task_id.split("::", 1)
            import httpx
            api_key = os.environ.get("API_KEY", "")
            remote_url = f"https://{workspace}--gooni-api.modal.run/status/{remote_task_id}"
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=5.0)) as client:
                    resp = await client.get(remote_url, headers={"X-API-Key": api_key})
                    if resp.status_code == 404:
                        raise HTTPException(
                            status_code=404,
                            detail=_error_payload(
                                code="task_not_found",
                                detail="Remote task not found.",
                                user_action="Verify task id and retry.",
                            ),
                        )
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                # If remote is unreachable or failing, return 502 Bad Gateway
                raise HTTPException(
                    status_code=502,
                    detail=_error_payload(
                        code="remote_status_unavailable",
                        detail=f"Remote status fetch failed: {str(e)}",
                        user_action="Retry shortly.",
                    ),
                )

        results_vol.reload()
        result = storage.get_task(task_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=_error_payload(
                    code="task_not_found",
                    detail=f"Task '{task_id}' not found.",
                    user_action="Verify task id and retry.",
                ),
            )

        pending_start_timeout_seconds = int(
            os.environ.get("PENDING_WORKER_START_TIMEOUT_SECONDS", "120")
        )
        if (
            result.status == TaskStatus.pending
            and (result.progress or 0) == 0
            and (result.stage is None or result.stage == "queued")
            and result.created_at is not None
        ):
            age_seconds = (datetime.now(result.created_at.tzinfo) - result.created_at).total_seconds()
            if age_seconds >= pending_start_timeout_seconds:
                storage.update_task_status(
                    task_id,
                    "failed",
                    progress=0,
                    error_msg=(
                        "Worker start timeout: no GPU worker picked up the task in time. "
                        "Check Modal quota/account health and retry."
                    ),
                    stage="failed",
                    stage_detail="worker_start_timeout",
                )
                results_vol.commit()
                result = storage.get_task(task_id) or result

        return result

    # ── GET /results/{task_id} ────────────────────────────────────────────────
    @api.get("/results/{task_id}", tags=["Generation"])
    async def get_result(
        task_id: str,
        _: str = Depends(verify_generation_session),
    ):
        if "::" in task_id:
            workspace, remote_task_id = task_id.split("::", 1)
            import httpx

            api_key = os.environ.get("API_KEY", "")
            remote_url = f"https://{workspace}--gooni-api.modal.run/results/{remote_task_id}"
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)) as client:
                    resp = await client.get(remote_url, headers={"X-API-Key": api_key})
                    if resp.status_code == 404:
                        raise HTTPException(
                            status_code=404,
                            detail=_error_payload(
                                code="result_not_found",
                                detail="Remote result not found.",
                                user_action="Verify task id or regenerate.",
                            ),
                        )
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "application/octet-stream")
                    return Response(content=resp.content, media_type=content_type)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=_error_payload(
                        code="remote_result_unavailable",
                        detail=f"Remote result fetch failed: {exc}",
                        user_action="Retry shortly.",
                    ),
                )

        results_vol.reload()
        task = storage.get_task(task_id)
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=_error_payload(
                    code="task_not_found",
                    detail="Task not found.",
                    user_action="Verify task id and retry.",
                ),
            )
        if task.status != TaskStatus.done:
            raise HTTPException(
                status_code=404,
                detail=_error_payload(
                    code="result_not_ready",
                    detail=f"Task is not done yet (status: {task.status}).",
                    user_action="Wait for completion and retry.",
                ),
            )

        # Derive the actual file path from the volume
        task_row = _get_raw_task(task_id)
        if not task_row or not task_row.get("result_path"):
            raise HTTPException(
                status_code=404,
                detail=_error_payload(
                    code="result_not_found",
                    detail="Result file not found.",
                    user_action="Regenerate the asset.",
                ),
            )

        fpath = task_row["result_path"]
        if not os.path.exists(fpath):
            raise HTTPException(
                status_code=410,
                detail=_error_payload(
                    code="result_file_missing",
                    detail="Result file missing from volume.",
                    user_action="Regenerate the asset.",
                ),
            )

        ext = Path(fpath).suffix.lstrip(".")
        media_types = {
            "mp4": "video/mp4", "webm": "video/webm",
            "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        }
        media_type = media_types.get(ext, "application/octet-stream")
        return FileResponse(fpath, media_type=media_type)

    # ── GET /preview/{task_id} ────────────────────────────────────────────────
    @api.get("/preview/{task_id}", tags=["Generation"])
    async def get_preview(
        task_id: str,
        _: str = Depends(verify_generation_session),
    ):
        if "::" in task_id:
            workspace, remote_task_id = task_id.split("::", 1)
            import httpx

            api_key = os.environ.get("API_KEY", "")
            remote_url = f"https://{workspace}--gooni-api.modal.run/preview/{remote_task_id}"
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=20.0, pool=5.0)) as client:
                    resp = await client.get(remote_url, headers={"X-API-Key": api_key})
                    if resp.status_code == 404:
                        raise HTTPException(status_code=404, detail=_error_payload(
                            code="preview_not_found", detail="Remote preview not found.", user_action="Verify task id or regenerate."))
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "image/jpeg")
                    return Response(content=resp.content, media_type=content_type)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=502, detail=_error_payload(
                    code="remote_preview_unavailable", detail=f"Remote preview fetch failed: {exc}", user_action="Retry shortly."))

        results_vol.reload()
        task_row = _get_raw_task(task_id)
        if not task_row:
            raise HTTPException(status_code=404, detail=_error_payload(
                code="task_not_found", detail="Task not found.", user_action="Verify task id and retry."))

        preview_path = task_row.get("preview_path")
        if not preview_path or not os.path.exists(preview_path):
            raise HTTPException(status_code=404, detail=_error_payload(
                code="preview_not_ready", detail="Preview not available yet.", user_action="Wait for completion and retry."))

        return FileResponse(preview_path, media_type="image/jpeg")

    # ── GET /gallery ──────────────────────────────────────────────────────────
    @api.get("/gallery", response_model=GalleryResponse, tags=["Gallery"])
    async def gallery(
        request: Request,
        page: int = Query(1, ge=1),
        per_page: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
        sort: str = Query("created_at"),
        model: Optional[str] = Query(None),
        type: Optional[str] = Query(None),
        _: str = Depends(verify_generation_session),
    ):
        results_vol.reload()
        items, total = storage.list_gallery(
            page=page,
            per_page=per_page,
            sort=sort,
            model_filter=model,
            type_filter=type,
        )
        request_base_url = str(request.base_url).rstrip("/")
        normalized_items = []
        for item in items:
            if item.result_url and item.preview_url:
                normalized_items.append(item)
                continue
            normalized_items.append(
                item.model_copy(
                    update={
                        "result_url": item.result_url or f"{request_base_url}/results/{item.id}",
                        "preview_url": item.preview_url or f"{request_base_url}/preview/{item.id}",
                    }
                )
            )
        return GalleryResponse(
            items=normalized_items,
            total=total,
            page=page,
            per_page=per_page,
            has_more=(page * per_page) < total,
        )

    # ── DELETE /gallery/{id} ──────────────────────────────────────────────────
    @api.delete(
        "/gallery/{task_id}",
        status_code=status.HTTP_200_OK,
        tags=["Gallery"],
    )
    async def delete_gallery_item(
        task_id: str,
        _: str = Depends(verify_generation_session),
    ):
        results_vol.reload()
        deleted = storage.delete_gallery_item(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=_error_payload(
                code="not_found", detail="Gallery item not found.", user_action="Verify item id and retry."))
        results_vol.commit()
        return DeleteResponse(deleted=True, id=task_id)

    # ═════════════════════════════════════════════════════════════════════════
    # ADMIN ENDPOINTS  (require X-Admin-Key header — rate-limited + audited)
    # ═════════════════════════════════════════════════════════════════════════

    import os as _os
    from deployer import deploy_account_async, deploy_all_accounts
    from admin_security import (
        _ensure_audit_table,
        get_admin_auth,
        verify_admin_key_header,
        ADMIN_SESSION_COOKIE,
    )

    _ensure_audit_table()

    @api.post("/admin/session", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin"])
    async def create_admin_session(
        response: Response,
        _ip: str = Depends(verify_admin_key_header("admin_session_create")),
    ):
        results_vol.reload()
        token, _ = storage.create_admin_session(idle_timeout_seconds=admin_idle_timeout_seconds)
        results_vol.commit()
        _set_session_cookie(
            response=response,
            key=ADMIN_SESSION_COOKIE,
            value=token,
            max_age=admin_idle_timeout_seconds,
        )
        return None

    @api.get("/admin/session", response_model=AdminSessionStateResponse, tags=["Admin"])
    async def get_admin_session_state(
        request: Request,
        _ip: str = Depends(get_admin_auth("admin_session_get")),
    ):
        token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "admin_session_missing",
                    "detail": "Admin session is missing.",
                    "user_action": "Login again to continue.",
                },
            )
        results_vol.reload()
        active, reason, _ = storage.validate_admin_session(token, touch=False)
        if not active:
            code = "admin_session_expired" if reason == "expired" else "admin_session_invalid"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": code,
                    "detail": "Admin session is invalid or expired.",
                    "user_action": "Login again to continue.",
                },
            )
        session_row = storage.get_admin_session(token)
        last_activity = None
        if session_row and session_row.get("last_activity_at"):
            try:
                last_activity = datetime.fromisoformat(session_row["last_activity_at"])
            except Exception:
                last_activity = None

        return AdminSessionStateResponse(
            active=True,
            idle_timeout_seconds=admin_idle_timeout_seconds,
            last_activity_at=last_activity,
        )

    @api.delete("/admin/session", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin"])
    async def delete_admin_session(
        response: Response,
        request: Request,
        _ip: str = Depends(get_admin_auth("admin_session_delete")),
    ):
        token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        if token:
            results_vol.reload()
            storage.revoke_admin_session(token)
            results_vol.commit()
        _delete_session_cookie(response, ADMIN_SESSION_COOKIE)
        return None

    # ── GET /admin/health — fast probe (also validates key) ─────────────────
    @api.get("/admin/health", tags=["Admin"])
    async def admin_health(_ip: str = Depends(get_admin_auth("health"))):
        results_vol.reload()
        ready = [a for a in acc_store.list_accounts() if a["status"] == "ready"]
        storage_ok = storage.check_storage_health()
        return {
            "ok": True,
            "storage_ok": storage_ok,
            "ready_accounts": len(ready),
            "diagnostics": storage.get_operational_snapshot(),
        }

    # ── POST /admin/accounts ─────────────────────────────────────────────────
    @api.post("/admin/accounts", tags=["Admin"], status_code=201)
    async def admin_add_account(
        label: str = Body(...),
        token_id: str = Body(...),
        token_secret: str = Body(...),
        _ip: str = Depends(get_admin_auth("add_account"))
    ):
        results_vol.reload()
        account_id = acc_store.add_account(
            label=label,
            token_id=token_id,
            token_secret=token_secret,
        )
        results_vol.commit()
        deploy_account_async(account_id)
        return {"id": account_id, "status": "pending", "message": "Deploying..."}

    # ── GET /admin/accounts ──────────────────────────────────────────────────
    @api.get("/admin/accounts", tags=["Admin"])
    async def admin_list_accounts(_ip: str = Depends(get_admin_auth("list_accounts"))):
        results_vol.reload()
        rows = acc_store.list_accounts()
        return {
            "accounts": rows,
            "diagnostics": storage.get_operational_snapshot(),
            "events": storage.list_operational_events(limit=30),
        }

    # ── DELETE /admin/accounts/{id} ──────────────────────────────────────────
    @api.delete("/admin/accounts/{account_id}", tags=["Admin"])
    async def admin_delete_account(account_id: str, _ip: str = Depends(get_admin_auth("delete_account"))):
        results_vol.reload()
        deleted = acc_store.delete_account(account_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=_error_payload(
                code="not_found", detail="Account not found.", user_action="Verify account id and retry."))
        results_vol.commit()
        return {"deleted": True, "id": account_id}

    # ── POST /admin/accounts/{id}/disable ────────────────────────────────────
    @api.post("/admin/accounts/{account_id}/disable", tags=["Admin"])
    async def admin_disable_account(account_id: str, _ip: str = Depends(get_admin_auth("disable_account"))):
        results_vol.reload()
        acc_store.disable_account(account_id)
        results_vol.commit()
        return {"id": account_id, "status": "disabled"}

    # ── POST /admin/accounts/{id}/enable ─────────────────────────────────────
    @api.post("/admin/accounts/{account_id}/enable", tags=["Admin"])
    async def admin_enable_account(account_id: str, _ip: str = Depends(get_admin_auth("enable_account"))):
        results_vol.reload()
        acc_store.enable_account(account_id)
        results_vol.commit()
        return {"id": account_id, "status": "ready"}

    # ── POST /admin/accounts/{id}/deploy ─────────────────────────────────────
    @api.post("/admin/accounts/{account_id}/deploy", tags=["Admin"])
    async def admin_deploy_account(account_id: str, _ip: str = Depends(get_admin_auth("deploy_account"))):
        if acc_store.get_account(account_id) is None:
            raise HTTPException(
                status_code=404,
                detail=_error_payload(
                    code="not_found",
                    detail="Account not found.",
                    user_action="Verify account id and retry.",
                ),
            )
        deploy_account_async(account_id)
        return {"id": account_id, "status": "checking", "message": "Deploy started, health-check in progress."}

    # ── POST /admin/deploy-all ────────────────────────────────────────────────
    @api.post("/admin/deploy-all", tags=["Admin"])
    async def admin_deploy_all(_ip: str = Depends(get_admin_auth("deploy_all"))):
        threads = deploy_all_accounts()
        return {"deploying": len(threads), "message": f"Deploying {len(threads)} account(s)..."}

    # ── GET /admin/logs — Returns recent audit log entries ────────────────────
    @api.get("/admin/logs", tags=["Admin"])
    async def admin_get_logs(limit: int = 100, _ip: str = Depends(get_admin_auth("read_logs"))):
        results_vol.reload()
        return {"logs": storage.get_audit_logs(limit=limit)}

    # ── Internal helper ───────────────────────────────────────────────────────
    def _get_raw_task(task_id: str) -> Optional[dict]:
        """Delegate to storage module for raw task access."""
        return storage.get_raw_task(task_id)

    return api
