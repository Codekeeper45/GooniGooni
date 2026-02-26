"""
Pydantic schemas for request/response validation.
Field names mirror exactly what configManager.buildPayload() sends from the frontend.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


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


class SessionStatus(str, Enum):
    active = "active"
    expired = "expired"
    revoked = "revoked"


class AccountStatus(str, Enum):
    pending = "pending"
    checking = "checking"
    ready = "ready"
    failed = "failed"
    disabled = "disabled"


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

    @model_validator(mode="before")
    @classmethod
    def normalize_video_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        model = normalized.get("model")
        if isinstance(model, ModelId):
            model = model.value
        if "cfg" in normalized and "cfg_scale" not in normalized:
            normalized["cfg_scale"] = normalized["cfg"]
        # Legacy callers may send guidance_scale for phr00t; normalize to cfg_scale.
        if model == "phr00t" and "guidance_scale" in normalized and "cfg_scale" not in normalized:
            normalized["cfg_scale"] = normalized["guidance_scale"]
        if model == "anisora" and normalized.get("steps") is None:
            normalized["steps"] = 8
        if model == "phr00t" and normalized.get("steps") is None:
            normalized["steps"] = 4
        return normalized

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

        # Enforce model/type pairing
        if model in {ModelId.anisora, ModelId.phr00t} and gen_type != GenerationType.video:
            raise ValueError(f"Model '{model.value}' requires type='video'")
        if model in {ModelId.pony, ModelId.flux} and gen_type != GenerationType.image:
            raise ValueError(f"Model '{model.value}' requires type='image'")

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

    @field_validator("steps")
    @classmethod
    def enforce_fixed_video_steps(cls, v: Optional[int], info: ValidationInfo) -> Optional[int]:
        if v is None:
            return v
        model = info.data.get("model")
        if isinstance(model, ModelId):
            model = model.value
        if model == "anisora" and v != 8:
            raise ValueError("For anisora, steps must be exactly 8")
        if model == "phr00t" and v != 4:
            raise ValueError("For phr00t, steps must be exactly 4")
        return v

    @field_validator("cfg_scale")
    @classmethod
    def enforce_fixed_phr00t_cfg(cls, v: Optional[float], info: ValidationInfo) -> Optional[float]:
        model = info.data.get("model")
        if isinstance(model, ModelId):
            model = model.value
        if model != "phr00t":
            return v
        if v is None:
            raise ValueError("For phr00t, cfg_scale must be exactly 1.0")
        if float(v) != 1.0:
            raise ValueError("For phr00t, cfg_scale must be exactly 1.0")
        return float(v)

    @staticmethod
    def _approx_bytes_from_data_uri(value: Optional[str]) -> int:
        if not value:
            return 0
        payload = value.split(",", 1)[1] if "," in value else value
        # base64 size approximation
        return int(len(payload) * 3 / 4)

    @model_validator(mode="after")
    def validate_mode_requirements_and_sizes(self):
        max_image_bytes = 12 * 1024 * 1024  # 12 MB decoded per image

        if self.mode in {"i2v", "img2img"} and not self.reference_image:
            raise ValueError("reference_image is required for i2v/img2img mode")
        if self.mode == "first_last_frame" and (not self.first_frame_image or not self.last_frame_image):
            raise ValueError("first_frame_image and last_frame_image are required for first_last_frame mode")
        if self.mode == "arbitrary_frame" and not self.arbitrary_frames:
            raise ValueError("arbitrary_frames must not be empty for arbitrary_frame mode")

        for field_name in ("reference_image", "first_frame_image", "last_frame_image"):
            value = getattr(self, field_name)
            if self._approx_bytes_from_data_uri(value) > max_image_bytes:
                raise ValueError(f"{field_name} exceeds max size of {max_image_bytes} bytes")

        for idx, item in enumerate(self.arbitrary_frames or []):
            if self._approx_bytes_from_data_uri(item.image) > max_image_bytes:
                raise ValueError(f"arbitrary_frames[{idx}].image exceeds max size of {max_image_bytes} bytes")

        return self


# ─── Responses ────────────────────────────────────────────────────────────────

class GenerateResponse(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.pending


class StatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int = Field(default=0, ge=0, le=100)
    stage: Optional[str] = None
    stage_detail: Optional[str] = None
    lane_mode: Optional[Literal["dedicated", "degraded_shared"]] = None
    fallback_reason: Optional[str] = None
    diagnostics: Optional[dict[str, Any]] = None
    result_url: Optional[str] = None
    preview_url: Optional[str] = None
    error_msg: Optional[str] = None
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
    preview_url: Optional[str] = None
    result_url: Optional[str] = None


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
    ok: Literal[True] = True


class GenerationSessionResponse(BaseModel):
    session_status: SessionStatus = SessionStatus.active
    expires_at: datetime


class GenerationSessionStateResponse(BaseModel):
    valid: bool
    active: bool
    expires_at: Optional[datetime] = None


class AdminSessionStateResponse(BaseModel):
    active: bool
    idle_timeout_seconds: int = 43200
    last_activity_at: Optional[datetime] = None


class ErrorResponse(BaseModel):
    code: str
    detail: str
    user_action: str


class ApiErrorEnvelope(BaseModel):
    detail: ErrorResponse


class AddAccountRequest(BaseModel):
    label: str
    token_id: str
    token_secret: str


class AccountResponse(BaseModel):
    id: str
    label: str
    workspace: Optional[str] = None
    status: AccountStatus
    use_count: int
    last_used: Optional[str] = None
    last_error: Optional[str] = None
    added_at: str
