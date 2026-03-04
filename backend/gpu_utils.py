"""
GPU utility functions for server-side GPU detection.
Parses nvidia-smi output to determine GPU capabilities.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger("gpu_utils")


@dataclass
class GPUInfo:
    detected: bool = False
    name: Optional[str] = None
    vram_total_mb: Optional[int] = None
    vram_free_mb: Optional[int] = None
    driver_version: Optional[str] = None
    cuda_version: Optional[str] = None
    vram_level: str = "red"  # green | yellow | orange | red

    def to_dict(self) -> dict:
        return asdict(self)


def compute_vram_level(vram_total_mb: Optional[int]) -> str:
    """Determine VRAM level from total VRAM in MB."""
    if vram_total_mb is None:
        return "red"
    if vram_total_mb >= 12288:
        return "green"
    if vram_total_mb >= 8192:
        return "yellow"
    if vram_total_mb >= 4096:
        return "orange"
    return "red"


def parse_nvidia_smi_csv(csv_output: str) -> GPUInfo:
    """
    Parse nvidia-smi CSV output line:
    "NVIDIA GeForce RTX 3060, 12288, 10240, 535.129.03"
    """
    if not csv_output or not csv_output.strip():
        return GPUInfo()

    first_line = csv_output.strip().split("\n")[0]
    parts = [s.strip() for s in first_line.split(",")]

    if len(parts) < 4:
        return GPUInfo()

    name = parts[0] or None
    try:
        vram_total_mb = int(parts[1]) if parts[1] else None
    except (ValueError, IndexError):
        vram_total_mb = None
    try:
        vram_free_mb = int(parts[2]) if parts[2] else None
    except (ValueError, IndexError):
        vram_free_mb = None
    driver_version = parts[3] if len(parts) > 3 and parts[3] else None

    vram_level = compute_vram_level(vram_total_mb)

    return GPUInfo(
        detected=True,
        name=name,
        vram_total_mb=vram_total_mb,
        vram_free_mb=vram_free_mb,
        driver_version=driver_version,
        vram_level=vram_level,
    )


def extract_cuda_version(nvidia_smi_output: str) -> Optional[str]:
    """Extract CUDA version from full nvidia-smi header output."""
    match = re.search(r"CUDA Version:\s*([\d.]+)", nvidia_smi_output)
    return match.group(1) if match else None


def query_gpu_info() -> GPUInfo:
    """
    Query GPU information via nvidia-smi.
    Returns GPUInfo with detected=False if nvidia-smi is unavailable.
    """
    no_gpu = GPUInfo()

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return no_gpu

        info = parse_nvidia_smi_csv(result.stdout)

        # Try to extract CUDA version from header
        try:
            header_result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if header_result.returncode == 0:
                info.cuda_version = extract_cuda_version(header_result.stdout)
        except Exception:
            pass

        return info

    except FileNotFoundError:
        logger.debug("nvidia-smi not found")
        return no_gpu
    except subprocess.TimeoutExpired:
        logger.warning("nvidia-smi timed out")
        return no_gpu
    except Exception as exc:
        logger.warning("GPU detection failed: %s", exc)
        return no_gpu
