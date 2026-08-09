"""Single-source configuration for the Pony image generator."""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "gooni-gooni-backend"
APP_VERSION = "2.0.0"

MODEL_CACHE_PATH = "/model-cache"
RESULTS_PATH = os.environ.get("RESULTS_PATH", "/results")
ITEMS_PATH = f"{RESULTS_PATH}/items"

MODEL_CACHE_VOLUME = os.environ.get("CACHE_VOLUME", "model-cache")
RESULTS_VOLUME_NAME = os.environ.get("RESULTS_VOLUME", "results")

PONY_MODEL_ID = os.environ.get(
    "PONY_MODEL_ID",
    "Polenov2024/Pony-Diffusion-V6-XL",
)
IMAGE_GPU = os.environ.get("IMAGE_GPU", "T4")
IMAGE_TIMEOUT = int(os.environ.get("IMAGE_TIMEOUT", "600"))
IMAGE_STARTUP_TIMEOUT = int(os.environ.get("IMAGE_STARTUP_TIMEOUT", "900"))
IMAGE_MAX_CONTAINERS = int(os.environ.get("IMAGE_MAX_CONTAINERS", "1"))

DEFAULT_PAGE_SIZE = 24
MAX_PAGE_SIZE = 100

PONY_CONTRACT = json.loads(
    Path(__file__).with_name("pony_contract.json").read_text(encoding="utf-8")
)
SAMPLERS = tuple(PONY_CONTRACT["samplers"])
_defaults = PONY_CONTRACT["defaults"]
_limits = PONY_CONTRACT["limits"]
_model = PONY_CONTRACT["model"]

MODELS_SCHEMA = [
    {
        "id": _model["id"],
        "name": _model["name"],
        "type": _model["type"],
        "description": "SDXL-based anime image generation",
        "modes": _model["modes"],
        "default_mode": _model["default_mode"],
        "parameters_schema": {
            "prompt": {"type": "string", "required": True, "max_length": _limits["prompt_max_length"]},
            "negative_prompt": {
                "type": "string",
                "default": _defaults["negative_prompt"],
                "max_length": _limits["negative_prompt_max_length"],
            },
            "width": {"type": "int", "default": _defaults["width"], **_limits["width"], "multiple_of": 8},
            "height": {"type": "int", "default": _defaults["height"], **_limits["height"], "multiple_of": 8},
            "steps": {"type": "int", "default": _defaults["steps"], **_limits["steps"]},
            "cfg_scale": {"type": "float", "default": _defaults["cfg_scale"], **_limits["cfg_scale"]},
            "sampler": {"type": "enum", "options": list(SAMPLERS), "default": _defaults["sampler"]},
            "clip_skip": {"type": "int", "default": _defaults["clip_skip"], **_limits["clip_skip"]},
            "denoising_strength": {
                "type": "float",
                "default": _defaults["denoising_strength"],
                **_limits["denoising_strength"],
                "modes": ["img2img"],
            },
            "seed": {"type": "int", "default": _defaults["seed"], **_limits["seed"]},
            "output_format": {
                "type": "enum",
                "options": PONY_CONTRACT["output_formats"],
                "default": _defaults["output_format"],
            },
            "reference_image": {"type": "image", "required_for": ["img2img"]},
        },
    }
]
