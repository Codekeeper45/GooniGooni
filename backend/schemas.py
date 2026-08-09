"""Strict API contract shared by every backend endpoint."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from config import PONY_CONTRACT

_defaults = PONY_CONTRACT["defaults"]
_limits = PONY_CONTRACT["limits"]


class TaskStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class GenerateRequest(BaseModel):
    """The complete and only supported generation payload."""

    model_config = ConfigDict(extra="forbid")

    model: Literal["pony"] = "pony"
    type: Literal["image"] = "image"
    mode: Literal["txt2img", "img2img"] = PONY_CONTRACT["model"]["default_mode"]
    prompt: str = Field(min_length=1, max_length=_limits["prompt_max_length"])
    negative_prompt: str = Field(
        default=_defaults["negative_prompt"],
        max_length=_limits["negative_prompt_max_length"],
    )
    width: int = Field(default=_defaults["width"], ge=_limits["width"]["min"], le=_limits["width"]["max"])
    height: int = Field(default=_defaults["height"], ge=_limits["height"]["min"], le=_limits["height"]["max"])
    steps: int = Field(default=_defaults["steps"], ge=_limits["steps"]["min"], le=_limits["steps"]["max"])
    cfg_scale: float = Field(
        default=_defaults["cfg_scale"],
        ge=_limits["cfg_scale"]["min"],
        le=_limits["cfg_scale"]["max"],
    )
    sampler: Literal[
        "Euler a",
        "DPM++ 2M Karras",
        "DPM++ SDE Karras",
    ] = _defaults["sampler"]
    clip_skip: int = Field(
        default=_defaults["clip_skip"],
        ge=_limits["clip_skip"]["min"],
        le=_limits["clip_skip"]["max"],
    )
    denoising_strength: float = Field(
        default=_defaults["denoising_strength"],
        ge=_limits["denoising_strength"]["min"],
        le=_limits["denoising_strength"]["max"],
    )
    seed: int = Field(default=_defaults["seed"], ge=_limits["seed"]["min"], le=_limits["seed"]["max"])
    output_format: Literal["png", "jpeg"] = _defaults["output_format"]
    reference_image: str | None = Field(default=None, max_length=20_000_000)

    @field_validator("prompt", "negative_prompt")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("width", "height")
    @classmethod
    def dimensions_are_diffusion_safe(cls, value: int) -> int:
        if value % 8:
            raise ValueError("dimensions must be divisible by 8")
        return value

    @model_validator(mode="after")
    def mode_matches_reference(self) -> "GenerateRequest":
        if self.width * self.height > _limits["max_pixels"]:
            raise ValueError(
                f"width × height must not exceed {_limits['max_pixels']} pixels"
            )
        if self.mode == "img2img" and not self.reference_image:
            raise ValueError("reference_image is required for img2img")
        if self.mode == "txt2img" and self.reference_image is not None:
            raise ValueError("reference_image is only accepted for img2img")
        return self


class GenerateResponse(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.pending
    message: str = "Generation queued"


class ResultSummary(BaseModel):
    id: str
    model: Literal["pony"] = "pony"
    mode: Literal["txt2img", "img2img"]
    prompt: str
    negative_prompt: str = ""
    width: int
    height: int
    steps: int
    cfg_scale: float
    sampler: str
    clip_skip: int
    denoising_strength: float
    seed: int
    output_format: Literal["png", "jpeg"]
    created_at: datetime


class StatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str
    result_url: str | None = None
    preview_url: str | None = None
    error: str | None = None
    result: ResultSummary | None = None


class GalleryItemResponse(ResultSummary):
    preview_url: str
    result_url: str


class GalleryResponse(BaseModel):
    items: list[GalleryItemResponse]
    total: int
    page: int
    per_page: int
    has_more: bool


class ModelsResponse(BaseModel):
    models: list[dict[str, Any]]


class DeleteResponse(BaseModel):
    deleted: bool
    id: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    app: str
    model: Literal["pony"] = "pony"
