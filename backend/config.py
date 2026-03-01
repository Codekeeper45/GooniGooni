"""
Configuration for the Gooni Gooni Modal backend.
All sensitive values come from Modal Secrets / environment variables.
"""
import os

# ─── App identity ──────────────────────────────────────────────────────────────
APP_NAME = "gooni-gooni-backend"

# Worker build identifier — bump manually after each modal deploy with breaking changes.
# Empty string disables the check (safe default).
WORKER_BUILD_ID: str = os.environ.get("WORKER_BUILD_ID", "")

# ─── Volume names ──────────────────────────────────────────────────────────────
MODEL_CACHE_VOLUME = os.environ.get("CACHE_VOLUME", "model-cache")
RESULTS_VOLUME_NAME = os.environ.get("RESULTS_VOLUME", "results")

# Internal mount paths inside the Modal container
MODEL_CACHE_PATH = "/model-cache"
RESULTS_PATH = "/results"
DB_PATH = f"{RESULTS_PATH}/gallery.db"

# ─── HuggingFace model identifiers ─────────────────────────────────────────────
# Override these via Modal Secrets / env vars for your private/licensed models.
MODEL_IDS: dict[str, str] = {
    # Video – Official Wan2.1 14B Diffusers (fallback since Index-anisora lacks diffusers format)
    # Repo: https://huggingface.co/Wan-AI/Wan2.1-T2V-14B-Diffusers
    "anisora": os.environ.get("ANISORA_MODEL_ID", "Wan-AI/Wan2.1-T2V-14B-Diffusers"),

    # Realistic video – Phr00t WAN 2.2 Rapid-AllInOne NSFW (single safetensors)
    # Repo: https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne
    # File loaded via from_single_file() — see models/phr00t.py
    "phr00t": os.environ.get("PHR00T_MODEL_ID", "Phr00t/WAN2.2-14B-Rapid-AllInOne"),

    # Anime image – Pony Diffusion V6 XL (full SDXL pipeline)
    # Repo: https://huggingface.co/Polenov2024/Pony-Diffusion-V6-XL
    "pony": os.environ.get("PONY_MODEL_ID", "Polenov2024/Pony-Diffusion-V6-XL"),

    # Realistic image – Flux.1 [dev] (base repo, NF4 quantized on-the-fly via BnB)
    # Repo: https://huggingface.co/black-forest-labs/FLUX.1-dev
    "flux": os.environ.get("FLUX_MODEL_ID", "black-forest-labs/FLUX.1-dev"),
}

# Subfolder is not used for the official diffusers model
ANISORA_SUBFOLDER = os.environ.get("ANISORA_SUBFOLDER", "")

# Filename of the Phr00t single-file checkpoint to download (latest Mega-v12)
PHR00T_FILENAME = os.environ.get(
    "PHR00T_FILENAME",
    "Mega-v12/wan2.2-rapid-mega-aio-nsfw-v12.2.safetensors",
)

# ─── GPU config ────────────────────────────────────────────────────────────────
VIDEO_GPU = os.environ.get("VIDEO_GPU", "A10G")  # 24 GB VRAM
IMAGE_GPU = os.environ.get("IMAGE_GPU", "A10G")  # 24 GB VRAM

# Maximum concurrent executions per function
VIDEO_CONCURRENCY = int(os.environ.get("VIDEO_CONCURRENCY", "1"))
IMAGE_CONCURRENCY = int(os.environ.get("IMAGE_CONCURRENCY", "2"))

# Timeout per generation job (seconds)
VIDEO_TIMEOUT = int(os.environ.get("VIDEO_TIMEOUT", "900"))   # 15 min
IMAGE_TIMEOUT = int(os.environ.get("IMAGE_TIMEOUT", "300"))   # 5 min

GPU_VRAM_BUDGET_GB = {
    "A10G": 24.0,
    "L4": 24.0,
    "T4": 16.0,
}
OOM_ERROR_CODE = "gpu_memory_exceeded"

# Dedicated video lane policy (AniSora / Phr00t keep warm independently)
VIDEO_LANE_WARM_MIN_CONTAINERS = int(os.environ.get("VIDEO_LANE_WARM_MIN_CONTAINERS", "1"))
VIDEO_LANE_WARM_MAX_CONTAINERS = int(os.environ.get("VIDEO_LANE_WARM_MAX_CONTAINERS", "1"))
IMAGE_LANE_WARM_MIN_CONTAINERS = int(os.environ.get("IMAGE_LANE_WARM_MIN_CONTAINERS", "1"))
IMAGE_LANE_WARM_MAX_CONTAINERS = int(os.environ.get("IMAGE_LANE_WARM_MAX_CONTAINERS", "1"))

# Degraded shared-worker queue policy
DEGRADED_QUEUE_MAX_DEPTH = int(os.environ.get("VIDEO_DEGRADED_QUEUE_MAX_DEPTH", "25"))
DEGRADED_QUEUE_MAX_WAIT_SECONDS = int(os.environ.get("VIDEO_DEGRADED_QUEUE_MAX_WAIT_SECONDS", "30"))
DEGRADED_QUEUE_OVERLOAD_CODE = "queue_overloaded"

# Dedicated-lane readiness/fallback policy
VIDEO_LANE_HEALTH_GRACE_SECONDS = int(os.environ.get("VIDEO_LANE_HEALTH_GRACE_SECONDS", "60"))
VIDEO_LANE_ASSIGNMENT_TIMEOUT_SECONDS = int(os.environ.get("VIDEO_LANE_ASSIGNMENT_TIMEOUT_SECONDS", "30"))
ENABLE_LANE_WARMUP = (os.environ.get("ENABLE_LANE_WARMUP", "1").strip().lower() in {"1", "true", "yes", "on"})
WARMUP_RETRIES = int(os.environ.get("WARMUP_RETRIES", "2"))
WARMUP_TIMEOUT_SECONDS = int(os.environ.get("WARMUP_TIMEOUT_SECONDS", "25"))

# Fixed video generation constraints (source-of-truth for backend validation/tests)
VIDEO_FIXED_CONSTRAINTS = {
    "anisora": {"steps": 50, "cfg_scale": 4.0},   # Optimal: 50 steps, CFG 4.0 (bfloat16 Wan2.1)
    "phr00t": {"steps": 40, "cfg_scale": 7.0},    # Optimal: 40 steps, CFG 7.0 (WAN 2.2 Rapid)
}

# ─── Gallery defaults ──────────────────────────────────────────────────────────
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Unified flow defaults (spec-aligned)
ARTIFACT_TTL_DAYS = int(os.environ.get("ARTIFACT_TTL_DAYS", "30"))
GEN_SESSION_MAX_ACTIVE_TASKS = int(os.environ.get("GEN_SESSION_MAX_ACTIVE_TASKS", "2"))
NO_READY_ACCOUNT_WAIT_SECONDS = int(os.environ.get("NO_READY_ACCOUNT_WAIT_SECONDS", "30"))

# ─── Model metadata (schema exposed via /models endpoint) ──────────────────────
MODELS_SCHEMA = [
    {
        "id": "anisora",
        "name": "Index-AniSora V3.2",
        "type": "video",
        "category": "hentai",
        "description": "High-quality anime video generation",
        "modes": ["t2v", "i2v", "first_last_frame", "arbitrary_frame"],
        "default_mode": "t2v",
        "fixed_parameters": {
            "steps": {"value": 50, "locked": True, "description": "Optimal for Wan2.1 14B anime quality"},
            "guidance_scale": {"value": 4.0, "locked": True, "description": "Optimal CFG for AniSora"},
        },
        "parameters_schema": {
            "num_frames": {"type": "int", "default": 81, "min": 49, "max": 161},
            "fps": {"type": "enum", "options": [8, 16, 24], "default": 16},
            "motion_score": {"type": "float", "default": 3.0, "min": 0.0, "max": 5.0},
            "reference_strength": {"type": "float", "default": 0.85, "min": 0.1, "max": 1.0},
            "denoising_strength": {"type": "float", "default": 0.7, "min": 0.0, "max": 1.0},
            "width": {"type": "int", "default": 720},
            "height": {"type": "int", "default": 1280},
            "seed": {"type": "int", "default": -1},
        },
    },
    {
        "id": "phr00t",
        "name": "Phr00t WAN 2.2 Rapid",
        "type": "video",
        "category": "realistic",
        "description": "Fast realistic NSFW video generation",
        "modes": ["t2v", "i2v", "first_last_frame"],
        "default_mode": "t2v",
        "fixed_parameters": {
            "steps": {"value": 40, "locked": True, "description": "Optimal for WAN 2.2 Rapid quality"},
            "cfg_scale": {"value": 7.0, "locked": True, "description": "Optimal CFG for WAN 2.2 Rapid prompt adherence"},
        },
        "parameters_schema": {
            "num_frames": {"type": "int", "default": 81, "min": 49, "max": 161},
            "fps": {"type": "enum", "options": [8, 16, 24], "default": 16},
            "lighting_variant": {"type": "enum", "options": ["high_noise", "low_noise"], "default": "low_noise"},
            "reference_strength": {"type": "float", "default": 1.0, "min": 0.5, "max": 1.0},
            "denoising_strength": {"type": "float", "default": 0.7, "min": 0.0, "max": 1.0},
            "width": {"type": "int", "default": 720},
            "height": {"type": "int", "default": 1280},
            "seed": {"type": "int", "default": -1},
        },
    },
    {
        "id": "pony",
        "name": "Pony Diffusion V6 XL",
        "type": "image",
        "category": "hentai",
        "description": "High-quality hentai image generation",
        "modes": ["txt2img", "img2img"],
        "default_mode": "txt2img",
        "parameters_schema": {
            "steps": {"type": "int", "default": 30, "min": 20, "max": 60},
            "cfg_scale": {"type": "float", "default": 6.0, "min": 1.0, "max": 12.0},
            "sampler": {"type": "enum", "options": ["Euler a", "DPM++ 2M Karras", "DPM++ SDE Karras"], "default": "DPM++ 2M Karras"},
            "clip_skip": {"type": "int", "default": 2, "min": 1, "max": 4},
            "denoising_strength": {"type": "float", "default": 0.7, "min": 0.0, "max": 1.0},
            "width": {"type": "int", "default": 1024},
            "height": {"type": "int", "default": 1024},
            "seed": {"type": "int", "default": -1},
        },
    },
    {
        "id": "flux",
        "name": "Flux.1 [dev] nf4",
        "type": "image",
        "category": "realistic",
        "description": "Realistic NSFW image generation",
        "modes": ["txt2img", "img2img"],
        "default_mode": "txt2img",
        "parameters_schema": {
            "steps": {"type": "int", "default": 25, "min": 15, "max": 50},
            "guidance_scale": {"type": "float", "default": 3.5, "min": 1.0, "max": 10.0},
            "sampler": {"type": "enum", "options": ["Euler", "flow-matching"], "default": "Euler"},
            "denoising_strength": {"type": "float", "default": 0.7, "min": 0.0, "max": 1.0},
            "width": {"type": "int", "default": 1024},
            "height": {"type": "int", "default": 1024},
            "seed": {"type": "int", "default": -1},
        },
    },
]
