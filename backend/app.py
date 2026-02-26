"""
Gooni Gooni Backend — Modal Application
========================================
Deploys a FastAPI server on Modal with:
  • Async video generation (A10G) — anisora, phr00t
  • Async image generation (T4)   — pony, flux
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
    .env({"HF_HOME": MODEL_CACHE_PATH, "TRANSFORMERS_CACHE": MODEL_CACHE_PATH})
    .add_local_dir(str(Path(__file__).parent), remote_path="/root")  # backend/ .py files
)

# Image generation image (T4 — 16 GB, includes bitsandbytes for NF4)
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
    .env({"HF_HOME": MODEL_CACHE_PATH, "TRANSFORMERS_CACHE": MODEL_CACHE_PATH})
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


def _get_video_pipeline(model_id_key: str):
    with _video_lock:
        if model_id_key in _video_pipeline_cache:
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

@app.function(
    image=video_image,
    gpu=os.environ.get("VIDEO_GPU", "A10G"),
    min_containers=int(os.environ.get("VIDEO_MIN_CONTAINERS", "1")),
    max_containers=int(os.environ.get("VIDEO_CONCURRENCY", "1")),
    timeout=900,
    volumes=_volumes,
    secrets=[api_secret, hf_secret],
)
def run_video_generation(request_dict: dict, task_id: str) -> dict:
    """
    Modal function that runs on A10G.
    Picks the correct pipeline from request_dict["model"] and executes inference.
    Returns {"result_path": ..., "preview_path": ...} or raises on failure.
    """
    sys.path.insert(0, "/root")  # backend/ files are copied to /root

    import storage
    results_vol.reload()
    storage.init_db()
    storage.update_task_status(task_id, "processing", progress=5)

    model_id_key = request_dict["model"]

    try:
        storage.update_task_status(task_id, "processing", progress=10)
        pipeline = _get_video_pipeline(model_id_key)
        storage.update_task_status(task_id, "processing", progress=20)

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


# ─── Image Generation Function ────────────────────────────────────────────────

@app.function(
    image=image_gen_image,
    gpu=os.environ.get("IMAGE_GPU", "T4"),
    min_containers=int(os.environ.get("IMAGE_MIN_CONTAINERS", "1")),
    max_containers=int(os.environ.get("IMAGE_CONCURRENCY", "2")),
    timeout=300,
    volumes=_volumes,
    secrets=[api_secret, hf_secret],
)
def run_image_generation(request_dict: dict, task_id: str) -> dict:
    """
    Modal function that runs on T4.
    Supports pony (SDXL) and flux (NF4) models.
    """
    sys.path.insert(0, "/root")

    import storage
    results_vol.reload()
    storage.init_db()
    storage.update_task_status(task_id, "processing", progress=5)

    model_id_key = request_dict["model"]

    try:
        storage.update_task_status(task_id, "processing", progress=10)
        pipeline = _get_image_pipeline(model_id_key)
        storage.update_task_status(task_id, "processing", progress=20)

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
    return JSONResponse({"status": "ok", "version": "1.0.0", "app": "gooni-gooni-backend"})


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

    from fastapi import Depends, FastAPI, HTTPException, Query, Request, status, Body
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse, Response

    import storage
    import accounts as acc_store
    from auth import verify_api_key, verify_generation_session, GENERATION_SESSION_COOKIE
    from config import MODELS_SCHEMA, DEFAULT_PAGE_SIZE, DB_PATH
    from router import router as account_router, NoReadyAccountError, MAX_FALLBACKS
    from deployer import deploy_account_async, deploy_all_accounts
    from schemas import (
        DeleteResponse,
        GalleryResponse,
        GenerateRequest,
        GenerateResponse,
        GenerationSessionResponse,
        GenerationSessionStateResponse,
        AdminSessionStateResponse,
        HealthResponse,
        ModelsResponse,
        StatusResponse,
        TaskStatus,
        AccountResponse,
    )

    # ── Init DB on cold start ─────────────────────────────────────────────────
    storage.init_db()
    acc_store.init_accounts_table()

    api = FastAPI(
        title="Gooni Gooni Backend",
        description="AI content generation API (images & videos)",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
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
    session_cookie_secure = os.environ.get("SESSION_COOKIE_SECURE", "1") != "0"
    session_cookie_samesite = os.environ.get("SESSION_COOKIE_SAMESITE", "none").lower()
    if session_cookie_samesite not in {"lax", "strict", "none"}:
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

    # ── GET /health ────────────────────────────────────────────────────────────
    @api.get("/health", response_model=HealthResponse, tags=["Info"])
    async def health_check():
        return HealthResponse()

    @api.post(
        "/auth/session",
        response_model=GenerationSessionResponse,
        status_code=status.HTTP_201_CREATED,
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
        return GenerationSessionResponse(expires_at=expires_at)

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
        return GenerationSessionStateResponse(active=True, expires_at=expires_at)

    # ── GET /models ────────────────────────────────────────────────────────────
    @api.get("/models", response_model=ModelsResponse, tags=["Info"])
    async def list_models(_: str = Depends(verify_api_key)):
        return ModelsResponse(models=MODELS_SCHEMA)

    # ── POST /generate_direct ──────────────────────────────────────────────────
    @api.post(
        "/generate_direct",
        response_model=GenerateResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["Generation"],
    )
    async def generate_direct(
        req: GenerateRequest,
        _: str = Depends(verify_api_key),
    ):
        """Internal endpoint for isolated Modal account execution."""
        results_vol.reload()
        params = req.model_dump(
            exclude={"prompt", "negative_prompt", "model", "type", "mode",
                     "width", "height", "seed",
                     "reference_image", "first_frame_image",
                     "last_frame_image", "arbitrary_frames"},
        )
        task_id = storage.create_task(
            model=req.model.value,
            gen_type=req.type.value,
            mode=req.mode,
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            parameters=params,
            width=req.width,
            height=req.height,
            seed=req.seed,
        )
        results_vol.commit()

        request_dict = req.model_dump()
        request_dict["model"] = req.model.value
        request_dict["type"] = req.type.value

        try:
            if req.type.value == "video":
                run_video_generation.spawn(request_dict, task_id)
            else:
                run_image_generation.spawn(request_dict, task_id)
        except Exception as exc:
            storage.update_task_status(task_id, "failed", error_msg=f"Spawn failed: {exc}")
            results_vol.commit()
            raise HTTPException(status_code=503, detail="Failed to enqueue generation task")

        return GenerateResponse(task_id=task_id, status=TaskStatus.pending)

    # ── POST /generate ─────────────────────────────────────────────────────────
    @api.post(
        "/generate",
        response_model=GenerateResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["Generation"],
    )
    async def generate(
        req: GenerateRequest,
        _: str = Depends(verify_generation_session),
    ):
        results_vol.reload()
        tried_accounts: list[str] = []
        last_error = ""

        # Default master behavior if no accounts or fallbacks fail
        async def _fallback_dispatch():
            # Persist local
            params = req.model_dump(
                exclude={"prompt", "negative_prompt", "model", "type", "mode",
                         "width", "height", "seed",
                         "reference_image", "first_frame_image",
                         "last_frame_image", "arbitrary_frames"},
            )
            local_task = storage.create_task(
                model=req.model.value,
                gen_type=req.type.value,
                mode=req.mode,
                prompt=req.prompt,
                negative_prompt=req.negative_prompt,
                parameters=params,
                width=req.width,
                height=req.height,
                seed=req.seed,
            )
            results_vol.commit()
            req_dict = req.model_dump()
            req_dict["model"] = req.model.value
            req_dict["type"] = req.type.value
            try:
                if req.type.value == "video":
                    run_video_generation.spawn(req_dict, local_task)
                else:
                    run_image_generation.spawn(req_dict, local_task)
            except Exception as exc:
                storage.update_task_status(local_task, "failed", error_msg=f"Spawn failed: {exc}")
                results_vol.commit()
                raise HTTPException(status_code=503, detail="Failed to enqueue local generation task")
            return GenerateResponse(task_id=local_task, status=TaskStatus.pending)

        import httpx
        api_key_env = os.environ.get("API_KEY", "")
        headers = {"X-API-Key": api_key_env} if api_key_env else {}

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
                    resp = await client.post(remote_url, json=req.model_dump(), headers=headers)
                    resp.raise_for_status()
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
            except Exception as exc:
                last_error = str(exc)
                if tried_accounts:
                    account_router.mark_failed(tried_accounts[-1], last_error)

        # Fallback to local dispatch
        return await _fallback_dispatch()

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
                        raise HTTPException(status_code=404, detail="Remote task not found")
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                # If remote is unreachable or failing, return 502 Bad Gateway
                raise HTTPException(status_code=502, detail=f"Remote status fetch failed: {str(e)}")

        results_vol.reload()
        result = storage.get_task(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
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
                        raise HTTPException(status_code=404, detail="Remote result not found")
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "application/octet-stream")
                    return Response(content=resp.content, media_type=content_type)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Remote result fetch failed: {exc}")

        results_vol.reload()
        task = storage.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.status != TaskStatus.done:
            raise HTTPException(
                status_code=425,
                detail=f"Task is not done yet (status: {task.status})",
            )

        # Derive the actual file path from the volume
        task_row = _get_raw_task(task_id)
        if not task_row or not task_row.get("result_path"):
            raise HTTPException(status_code=404, detail="Result file not found")

        fpath = task_row["result_path"]
        if not os.path.exists(fpath):
            raise HTTPException(status_code=404, detail="Result file missing from volume")

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
                        raise HTTPException(status_code=404, detail="Remote preview not found")
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "image/jpeg")
                    return Response(content=resp.content, media_type=content_type)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Remote preview fetch failed: {exc}")

        results_vol.reload()
        task_row = _get_raw_task(task_id)
        if not task_row:
            raise HTTPException(status_code=404, detail="Task not found")

        preview_path = task_row.get("preview_path")
        if not preview_path or not os.path.exists(preview_path):
            raise HTTPException(status_code=404, detail="Preview not available yet")

        return FileResponse(preview_path, media_type="image/jpeg")

    # ── GET /gallery ──────────────────────────────────────────────────────────
    @api.get("/gallery", response_model=GalleryResponse, tags=["Gallery"])
    async def gallery(
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
        return GalleryResponse(
            items=items,
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
            raise HTTPException(status_code=404, detail="Item not found")
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
        ready = [a for a in acc_store.list_accounts() if a["status"] == "ready"]
        return {"ok": True, "ready_accounts": len(ready)}

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
        return {"accounts": rows}

    # ── DELETE /admin/accounts/{id} ──────────────────────────────────────────
    @api.delete("/admin/accounts/{account_id}", tags=["Admin"])
    async def admin_delete_account(account_id: str, _ip: str = Depends(get_admin_auth("delete_account"))):
        results_vol.reload()
        deleted = acc_store.delete_account(account_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Account not found")
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
            raise HTTPException(status_code=404, detail="Account not found")
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
        import sqlite3 as _sql
        from config import DB_PATH as _db
        results_vol.reload()
        if not os.path.exists(_db):
            return {"logs": []}
        conn = _sql.connect(_db)
        conn.row_factory = _sql.Row
        rows = conn.execute(
            "SELECT * FROM admin_audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return {"logs": [dict(r) for r in rows]}

    # ── Internal helper ───────────────────────────────────────────────────────
    def _get_raw_task(task_id: str) -> Optional[dict]:
        """Return raw task dict from DB for file-serving endpoints."""
        import sqlite3
        from config import DB_PATH
        if not os.path.exists(DB_PATH):
            return None
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    return api
