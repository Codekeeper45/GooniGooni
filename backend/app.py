"""Gooni Gooni: one reliable Pony image-generation vertical slice."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import modal

from config import (
    APP_NAME,
    APP_VERSION,
    IMAGE_GPU,
    IMAGE_MAX_CONTAINERS,
    IMAGE_STARTUP_TIMEOUT,
    IMAGE_TIMEOUT,
    MODEL_CACHE_PATH,
    MODELS_SCHEMA,
    PONY_MODEL_ID,
    RESULTS_PATH,
)

app = modal.App(APP_NAME)
model_cache_vol = modal.Volume.from_name("model-cache", create_if_missing=True)
results_vol = modal.Volume.from_name("results", create_if_missing=True)
api_secret = modal.Secret.from_name("gooni-api-key")

_common_packages = [
    "fastapi==0.115.6",
    "pydantic==2.10.4",
    "Pillow==11.1.0",
]

gpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        *_common_packages,
        "torch==2.4.0",
        "torchvision==0.19.0",
        "diffusers==0.32.2",
        "transformers==4.46.3",
        "accelerate==1.2.1",
        "huggingface_hub==0.27.1",
        "safetensors==0.4.5",
        "numpy==1.26.4",
        "torchsde==0.2.6",
    )
    .env({"HF_HOME": MODEL_CACHE_PATH})
    .add_local_dir(str(Path(__file__).parent), remote_path="/root")
)

api_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(*_common_packages)
    .add_local_dir(str(Path(__file__).parent), remote_path="/root")
)


@app.cls(
    image=gpu_image,
    gpu=IMAGE_GPU,
    min_containers=0,
    max_containers=IMAGE_MAX_CONTAINERS,
    timeout=IMAGE_TIMEOUT,
    startup_timeout=IMAGE_STARTUP_TIMEOUT,
    scaledown_window=300,
    volumes={
        MODEL_CACHE_PATH: model_cache_vol,
        RESULTS_PATH: results_vol,
    },
)
class PonyGenerator:
    """Loads the model once and reuses it for every call in the container."""

    @modal.enter()
    def load_model(self) -> None:
        sys.path.insert(0, "/root")
        from models.pony import PonyPipeline

        self.pipeline = PonyPipeline(PONY_MODEL_ID)
        self.pipeline.load(MODEL_CACHE_PATH)
        model_cache_vol.commit()

    @modal.method()
    def generate(self, request: dict) -> dict:
        sys.path.insert(0, "/root")
        import storage

        result_id = str(uuid.uuid4())
        try:
            _, _, resolved_seed = self.pipeline.generate(
                request,
                result_id,
                RESULTS_PATH,
            )
            manifest = storage.write_manifest(result_id, request, resolved_seed)
            results_vol.commit()
            return manifest
        except Exception:
            # No manifest is written for partial output, so it can never appear
            # as a successful gallery item.
            raise


def _public_error(exc: Exception) -> str:
    """Return a useful message without leaking credentials or full tracebacks."""
    name = type(exc).__name__
    message = " ".join(str(exc).split())
    if len(message) > 500:
        message = message[:497] + "..."
    return f"{name}: {message}" if message else name


@app.function(
    image=api_image,
    volumes={RESULTS_PATH: results_vol},
    secrets=[api_secret],
    min_containers=1,
    max_containers=2,
)
@modal.concurrent(max_inputs=50)
@modal.asgi_app(label="gooni-api")
def fastapi_app():
    sys.path.insert(0, "/root")

    from fastapi import Depends, FastAPI, HTTPException, Query, status
    from fastapi.middleware.cors import CORSMiddleware
    import asyncio
    import mimetypes

    from fastapi.responses import Response

    import storage
    from auth import verify_api_key
    from schemas import (
        DeleteResponse,
        GalleryItemResponse,
        GalleryResponse,
        GenerateRequest,
        GenerateResponse,
        HealthResponse,
        ModelsResponse,
        ResultSummary,
        StatusResponse,
        TaskStatus,
    )

    api = FastAPI(
        title="Gooni Gooni Pony API",
        description="Reliable Pony Diffusion image generation",
        version=APP_VERSION,
    )
    configured_origins = [
        value.strip()
        for value in os.environ.get("CORS_ORIGINS", "*").split(",")
        if value.strip()
    ]
    api.add_middleware(
        CORSMiddleware,
        allow_origins=configured_origins or ["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
    # Modal Volume cannot reload while another request has a file open. Every
    # volume read is therefore reloaded and copied to memory under this lock.
    volume_lock = asyncio.Lock()

    def completed_status(task_id: str, output: dict) -> StatusResponse:
        summary = ResultSummary(**output)
        result_id = summary.id
        return StatusResponse(
            task_id=task_id,
            status=TaskStatus.done,
            message="Generation completed",
            result_url=f"/results/{result_id}",
            preview_url=f"/preview/{result_id}",
            result=summary,
        )

    @api.get("/health", response_model=HealthResponse, tags=["Info"])
    async def health() -> HealthResponse:
        return HealthResponse(
            version=APP_VERSION,
            app=APP_NAME,
        )

    @api.get("/models", response_model=ModelsResponse, tags=["Info"])
    async def models(_: str = Depends(verify_api_key)) -> ModelsResponse:
        return ModelsResponse(models=MODELS_SCHEMA)

    @api.post(
        "/generate",
        response_model=GenerateResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["Generation"],
    )
    async def generate(
        request: GenerateRequest,
        _: str = Depends(verify_api_key),
    ) -> GenerateResponse:
        try:
            call = PonyGenerator().generate.spawn(request.model_dump())
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Could not queue generation: {_public_error(exc)}",
            ) from exc
        return GenerateResponse(task_id=call.object_id)

    @api.get(
        "/status/{task_id}",
        response_model=StatusResponse,
        tags=["Generation"],
    )
    async def get_status(
        task_id: str,
        _: str = Depends(verify_api_key),
    ) -> StatusResponse:
        try:
            call = modal.FunctionCall.from_id(task_id)
            output = call.get(timeout=0)
            return completed_status(task_id, output)
        except TimeoutError:
            return StatusResponse(
                task_id=task_id,
                status=TaskStatus.processing,
                message="Queued or generating on GPU",
            )
        except modal.exception.OutputExpiredError as exc:
            return StatusResponse(
                task_id=task_id,
                status=TaskStatus.failed,
                message="Task record expired",
                error=_public_error(exc),
            )
        except Exception as exc:
            error_text = _public_error(exc)
            if "cancel" in error_text.lower() or "terminated" in error_text.lower():
                return StatusResponse(
                    task_id=task_id,
                    status=TaskStatus.cancelled,
                    message="Generation cancelled",
                )
            return StatusResponse(
                task_id=task_id,
                status=TaskStatus.failed,
                message="Generation failed",
                error=error_text,
            )

    @api.delete(
        "/tasks/{task_id}",
        response_model=StatusResponse,
        tags=["Generation"],
    )
    async def cancel_task(
        task_id: str,
        _: str = Depends(verify_api_key),
    ) -> StatusResponse:
        try:
            call = modal.FunctionCall.from_id(task_id)
            try:
                output = call.get(timeout=0)
                return completed_status(task_id, output)
            except TimeoutError:
                pass
            call.cancel()
        except Exception as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Could not cancel task: {_public_error(exc)}",
            ) from exc
        return StatusResponse(
            task_id=task_id,
            status=TaskStatus.cancelled,
            message="Generation cancelled",
        )

    @api.get("/gallery", response_model=GalleryResponse, tags=["Gallery"])
    async def gallery(
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=24, ge=1, le=100),
        _: str = Depends(verify_api_key),
    ) -> GalleryResponse:
        async with volume_lock:
            results_vol.reload()
            rows, total = storage.list_gallery(page, per_page)
        items = [
            GalleryItemResponse(
                **row,
                preview_url=f"/preview/{row['id']}",
                result_url=f"/results/{row['id']}",
            )
            for row in rows
        ]
        return GalleryResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            has_more=page * per_page < total,
        )

    @api.get("/results/{result_id}", tags=["Gallery"])
    async def result_file(
        result_id: str,
        _: str = Depends(verify_api_key),
    ):
        async with volume_lock:
            try:
                results_vol.reload()
                path = storage.get_result_path(result_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail="Result not found") from exc
            if not path:
                raise HTTPException(status_code=404, detail="Result not found")
            content = Path(path).read_bytes()
        media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return Response(content=content, media_type=media_type)

    @api.get("/preview/{result_id}", tags=["Gallery"])
    async def preview_file(
        result_id: str,
        _: str = Depends(verify_api_key),
    ):
        async with volume_lock:
            try:
                results_vol.reload()
                path = storage.get_preview_path(result_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail="Preview not found") from exc
            if not path:
                raise HTTPException(status_code=404, detail="Preview not found")
            content = Path(path).read_bytes()
        return Response(content=content, media_type="image/jpeg")

    @api.delete(
        "/gallery/{result_id}",
        response_model=DeleteResponse,
        tags=["Gallery"],
    )
    async def delete_gallery_item(
        result_id: str,
        _: str = Depends(verify_api_key),
    ) -> DeleteResponse:
        async with volume_lock:
            results_vol.reload()
            try:
                deleted = storage.delete_gallery_item(result_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail="Item not found") from exc
            if not deleted:
                raise HTTPException(status_code=404, detail="Item not found")
            results_vol.commit()
        return DeleteResponse(deleted=True, id=result_id)

    return api
