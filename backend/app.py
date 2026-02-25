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
from __future__ import annotations

import json
import mimetypes
import os
import sys
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


# ─── Docker Images ────────────────────────────────────────────────────────────

# Base Python packages shared by all images
_base_pkgs = [
    "fastapi>=0.111",
    "uvicorn[standard]",
    "pydantic>=2",
    "Pillow",
    "imageio[ffmpeg]",
    "huggingface_hub",
]

# Video generation image (A10G — 24 GB)
video_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        *_base_pkgs,
        "torch==2.3.1",
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
        "torch==2.3.1",
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

# ─── Video Generation Function ────────────────────────────────────────────────

@app.function(
    image=video_image,
    gpu=os.environ.get("VIDEO_GPU", "A10G"),
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
    storage.init_db()
    storage.update_task_status(task_id, "processing", progress=5)

    model_id_key = request_dict["model"]

    # Import the right pipeline
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

    storage.update_task_status(task_id, "processing", progress=10)
    pipeline.load(MODEL_CACHE_PATH)

    storage.update_task_status(task_id, "processing", progress=20)

    try:
        result_path, preview_path = pipeline.generate(request_dict, task_id, RESULTS_PATH)
        results_vol.commit()  # Flush to volume
        storage.update_task_status(
            task_id, "done", progress=100,
            result_path=result_path,
            preview_path=preview_path,
        )
        return {"result_path": result_path, "preview_path": preview_path}
    except Exception as exc:
        storage.update_task_status(task_id, "failed", error_msg=str(exc))
        raise


# ─── Image Generation Function ────────────────────────────────────────────────

@app.function(
    image=image_gen_image,
    gpu=os.environ.get("IMAGE_GPU", "T4"),
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
    storage.init_db()
    storage.update_task_status(task_id, "processing", progress=5)

    model_id_key = request_dict["model"]

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

    storage.update_task_status(task_id, "processing", progress=10)
    pipeline.load(MODEL_CACHE_PATH)

    storage.update_task_status(task_id, "processing", progress=20)

    try:
        result_path, preview_path = pipeline.generate(request_dict, task_id, RESULTS_PATH)
        results_vol.commit()
        storage.update_task_status(
            task_id, "done", progress=100,
            result_path=result_path,
            preview_path=preview_path,
        )
        return {"result_path": result_path, "preview_path": preview_path}
    except Exception as exc:
        storage.update_task_status(task_id, "failed", error_msg=str(exc))
        raise


# ─── FastAPI Server ───────────────────────────────────────────────────────────

@app.function(
    image=api_image,
    volumes=_volumes,
    secrets=[api_secret],
    min_containers=0,
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
    secrets=[api_secret, admin_secret],
    min_containers=0,
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

    from fastapi import Depends, FastAPI, HTTPException, Query, status
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse, Response
    from pydantic import BaseModel as PydanticBase

    import storage
    import accounts as acc_store
    from auth import verify_api_key
    from config import MODELS_SCHEMA, DEFAULT_PAGE_SIZE, DB_PATH
    from router import router as account_router, NoReadyAccountError, MAX_FALLBACKS
    from deployer import deploy_account_async, deploy_all_accounts
    from schemas import (
        DeleteResponse,
        GalleryResponse,
        GenerateRequest,
        GenerateResponse,
        HealthResponse,
        ModelsResponse,
        StatusResponse,
        TaskStatus,
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

    # Allow the frontend dev server and any deployed UI origin
    api.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",   # Tighten in production to your domain
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── GET /health ────────────────────────────────────────────────────────────
    @api.get("/health", response_model=HealthResponse, tags=["Info"])
    async def health_check():
        return HealthResponse()

    # ── GET /models ────────────────────────────────────────────────────────────
    @api.get("/models", response_model=ModelsResponse, tags=["Info"])
    async def list_models(_: str = Depends(verify_api_key)):
        return ModelsResponse(models=MODELS_SCHEMA)

    # ── POST /generate ─────────────────────────────────────────────────────────
    @api.post(
        "/generate",
        response_model=GenerateResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["Generation"],
    )
    async def generate(
        req: GenerateRequest,
        _: str = Depends(verify_api_key),
    ):
        # Persist the task immediately
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

        # ── Account rotation: pick account with fallback ───────────────────────
        request_dict = req.model_dump()
        request_dict["model"] = req.model.value
        request_dict["type"] = req.type.value

        tried_accounts: list[str] = []
        dispatched = False
        last_error = ""

        for attempt in range(MAX_FALLBACKS + 1):
            try:
                if attempt == 0:
                    account = account_router.pick()
                else:
                    account = account_router.pick_with_fallback(tried=tried_accounts)

                tried_accounts.append(account["id"])

                # Dispatch the right Modal function (non-blocking .spawn())
                if req.type.value == "video":
                    run_video_generation.spawn(request_dict, task_id)
                else:
                    run_image_generation.spawn(request_dict, task_id)

                account_router.mark_success(account["id"])
                dispatched = True
                break

            except NoReadyAccountError:
                # No accounts at all — fall through to single-account mode
                break
            except Exception as exc:
                last_error = str(exc)
                if tried_accounts:
                    account_router.mark_failed(tried_accounts[-1], last_error)

        if not dispatched:
            # Fallback: dispatch without account routing (uses default Modal auth)
            if req.type.value == "video":
                run_video_generation.spawn(request_dict, task_id)
            else:
                run_image_generation.spawn(request_dict, task_id)

        return GenerateResponse(task_id=task_id, status=TaskStatus.pending)

    # ── GET /status/{task_id} ──────────────────────────────────────────────────
    @api.get(
        "/status/{task_id}",
        response_model=StatusResponse,
        tags=["Generation"],
    )
    async def get_status(
        task_id: str,
        _: str = Depends(verify_api_key),
    ):
        result = storage.get_task(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return result

    # ── GET /results/{task_id} ────────────────────────────────────────────────
    @api.get("/results/{task_id}", tags=["Generation"])
    async def get_result(
        task_id: str,
        _: str = Depends(verify_api_key),
    ):
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
        _: str = Depends(verify_api_key),
    ):
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
        _: str = Depends(verify_api_key),
    ):
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
        _: str = Depends(verify_api_key),
    ):
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
    from admin_security import _ensure_audit_table, get_admin_auth

    _ensure_audit_table()

    class AddAccountRequest(PydanticBase):
        label: str
        token_id: str
        token_secret: str

    class AccountResponse(PydanticBase):
        id: str
        label: str
        workspace: Optional[str]
        status: str
        use_count: int
        last_used: Optional[str]
        last_error: Optional[str]
        added_at: str

    # ── GET /admin/health — fast probe (also validates key) ─────────────────
    @api.get("/admin/health", tags=["Admin"])
    async def admin_health(_ip: str = Depends(get_admin_auth("health"))):
        ready = [a for a in acc_store.list_accounts() if a["status"] == "ready"]
        return {"ok": True, "ready_accounts": len(ready)}

    # ── POST /admin/accounts ─────────────────────────────────────────────────
    @api.post("/admin/accounts", tags=["Admin"], status_code=201)
    async def admin_add_account(body: AddAccountRequest, _ip: str = Depends(get_admin_auth("add_account"))):
        account_id = acc_store.add_account(
            label=body.label,
            token_id=body.token_id,
            token_secret=body.token_secret,
        )
        deploy_account_async(account_id)
        return {"id": account_id, "status": "pending", "message": "Deploying..."}

    # ── GET /admin/accounts ──────────────────────────────────────────────────
    @api.get("/admin/accounts", tags=["Admin"])
    async def admin_list_accounts(_ip: str = Depends(get_admin_auth("list_accounts"))):
        rows = acc_store.list_accounts()
        return {"accounts": rows}

    # ── DELETE /admin/accounts/{id} ──────────────────────────────────────────
    @api.delete("/admin/accounts/{account_id}", tags=["Admin"])
    async def admin_delete_account(account_id: str, _ip: str = Depends(get_admin_auth("delete_account"))):
        deleted = acc_store.delete_account(account_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"deleted": True, "id": account_id}

    # ── POST /admin/accounts/{id}/disable ────────────────────────────────────
    @api.post("/admin/accounts/{account_id}/disable", tags=["Admin"])
    async def admin_disable_account(account_id: str, _ip: str = Depends(get_admin_auth("disable_account"))):
        acc_store.disable_account(account_id)
        return {"id": account_id, "status": "disabled"}

    # ── POST /admin/accounts/{id}/enable ─────────────────────────────────────
    @api.post("/admin/accounts/{account_id}/enable", tags=["Admin"])
    async def admin_enable_account(account_id: str, _ip: str = Depends(get_admin_auth("enable_account"))):
        acc_store.enable_account(account_id)
        return {"id": account_id, "status": "ready"}

    # ── POST /admin/accounts/{id}/deploy ─────────────────────────────────────
    @api.post("/admin/accounts/{account_id}/deploy", tags=["Admin"])
    async def admin_deploy_account(account_id: str, _ip: str = Depends(get_admin_auth("deploy_account"))):
        if acc_store.get_account(account_id) is None:
            raise HTTPException(status_code=404, detail="Account not found")
        deploy_account_async(account_id)
        return {"id": account_id, "status": "pending", "message": "Deploying..."}

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
