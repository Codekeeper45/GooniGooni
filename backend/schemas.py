"""
Pydantic schemas for request/response validation.
Field names mirror exactly what configManager.buildPayload() sends from the frontend.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ─── Enums ────────────────────────────────────────────────────────────────────

class ModelId(str, Enum):
    anisora = "anisora"
    phr00t = "phr00t"
    pony = "pony"
    flux = "flux"


class GenerationType(str, Enum):
    image = "image"
    video = "video"


class TaskStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


# ─── Nested models ────────────────────────────────────────────────────────────

class ArbitraryFrame(BaseModel):
    """A single keyframe for anisora arbitrary_frame mode."""
    frame_index: int = Field(..., ge=0, le=160)
    image: str  # base64-encoded image data URI
    strength: float = Field(default=0.85, ge=0.1, le=1.0)


# ─── Request ──────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    """
    Payload sent by the frontend via configManager.buildPayload().
    All image data is transmitted as base64 data URIs (data:image/...;base64,...).
    """
    # ── Required ──────────────────────────────────────────────────────────────
    model: ModelId
    type: GenerationType
    mode: str  # t2v | i2v | first_last_frame | arbitrary_frame | txt2img | img2img

    # ── Common parameters ─────────────────────────────────────────────────────
    prompt: str = Field(..., min_length=1, max_length=2000)
    negative_prompt: str = Field(default="", max_length=1000)
    width: int = Field(default=720, ge=256, le=2048)
    height: int = Field(default=1280, ge=256, le=2048)
    seed: int = Field(default=-1, ge=-1, le=2147483647)
    output_format: Literal["mp4", "webm", "png", "jpeg"] = "mp4"

    # ── Video parameters ──────────────────────────────────────────────────────
    num_frames: Optional[int] = Field(default=81, ge=1, le=241)
    fps: Optional[int] = Field(default=16)
    motion_score: Optional[float] = Field(default=3.0, ge=0.0, le=5.0)
    guidance_scale: Optional[float] = Field(default=1.0, ge=0.0, le=20.0)
    cfg_scale: Optional[float] = Field(default=1.0, ge=0.0, le=20.0)
    steps: Optional[int] = Field(default=None, ge=1, le=150)
    lighting_variant: Optional[Literal["high_noise", "low_noise"]] = "low_noise"

    # ── Reference image fields (base64 data URIs or None) ─────────────────────
    reference_strength: Optional[float] = Field(default=0.85, ge=0.0, le=1.0)
    reference_image: Optional[str] = None      # i2v or img2img
    first_frame_image: Optional[str] = None   # first_last_frame
    last_frame_image: Optional[str] = None    # first_last_frame
    arbitrary_frames: Optional[List[ArbitraryFrame]] = []

    # ── Image-specific parameters ─────────────────────────────────────────────
    sampler: Optional[str] = None
    clip_skip: Optional[int] = Field(default=2, ge=1, le=4)
    denoising_strength: Optional[float] = Field(default=0.7, ge=0.0, le=1.0)
    first_strength: Optional[float] = Field(default=1.0, ge=0.5, le=1.0)
    last_strength: Optional[float] = Field(default=1.0, ge=0.5, le=1.0)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str, info: Any) -> str:
        model = info.data.get("model")
        gen_type = info.data.get("type")

        video_modes = {"t2v", "i2v", "first_last_frame", "arbitrary_frame"}
        image_modes = {"txt2img", "img2img"}

        if gen_type == GenerationType.video and v not in video_modes:
            raise ValueError(f"Invalid mode '{v}' for video model. Valid: {video_modes}")
        if gen_type == GenerationType.image and v not in image_modes:
            raise ValueError(f"Invalid mode '{v}' for image model. Valid: {image_modes}")

        # arbitrary_frame only for anisora
        if v == "arbitrary_frame" and model != ModelId.anisora:
            raise ValueError("arbitrary_frame mode is only supported by anisora")

        return v

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("prompt must not be empty")
        return v


# ─── Responses ────────────────────────────────────────────────────────────────

class GenerateResponse(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.pending


class StatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int = Field(default=0, ge=0, le=100)
    result_url: Optional[str] = None
    preview_url: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GalleryItemResponse(BaseModel):
    id: str
    model: str
    type: str
    mode: str
    prompt: str
    negative_prompt: str = ""
    parameters: dict[str, Any] = {}
    width: int
    height: int
    seed: int
    created_at: datetime
    preview_url: str
    result_url: str


class GalleryResponse(BaseModel):
    items: List[GalleryItemResponse]
    total: int
    page: int
    per_page: int
    has_more: bool


class ModelsResponse(BaseModel):
    models: List[dict[str, Any]]


class DeleteResponse(BaseModel):
    deleted: bool
    id: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = "1.0.0"
    app: str = "gooni-gooni-backend"


class AddAccountRequest(BaseModel):
    label: str
    token_id: str
    token_secret: str


class AccountResponse(BaseModel):
    id: str
    label: str
    workspace: Optional[str] = None
    status: str
    use_count: int
    last_used: Optional[str] = None
    last_error: Optional[str] = None
    added_at: str
