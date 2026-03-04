"""
Unit tests for GPU detection via nvidia-smi parsing.
Tests: CSV parsing, vram_level thresholds, missing nvidia-smi, malformed output.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from gpu_utils import (
    GPUInfo,
    compute_vram_level,
    parse_nvidia_smi_csv,
    extract_cuda_version,
    query_gpu_info,
)


# ─── vram_level thresholds ────────────────────────────────────────────────────

class TestComputeVramLevel:
    def test_green_12gb(self):
        assert compute_vram_level(12288) == "green"

    def test_green_24gb(self):
        assert compute_vram_level(24576) == "green"

    def test_yellow_8gb(self):
        assert compute_vram_level(8192) == "yellow"

    def test_yellow_11gb(self):
        assert compute_vram_level(11264) == "yellow"

    def test_orange_4gb(self):
        assert compute_vram_level(4096) == "orange"

    def test_orange_6gb(self):
        assert compute_vram_level(6144) == "orange"

    def test_red_2gb(self):
        assert compute_vram_level(2048) == "red"

    def test_red_0(self):
        assert compute_vram_level(0) == "red"

    def test_none(self):
        assert compute_vram_level(None) == "red"

    def test_boundary_12287(self):
        assert compute_vram_level(12287) == "yellow"

    def test_boundary_8191(self):
        assert compute_vram_level(8191) == "orange"

    def test_boundary_4095(self):
        assert compute_vram_level(4095) == "red"


# ─── nvidia-smi CSV parsing ──────────────────────────────────────────────────

class TestParseNvidiaSmiCsv:
    def test_standard_output(self):
        csv = "NVIDIA GeForce RTX 3060, 12288, 10240, 535.129.03"
        info = parse_nvidia_smi_csv(csv)
        assert info.detected is True
        assert info.name == "NVIDIA GeForce RTX 3060"
        assert info.vram_total_mb == 12288
        assert info.vram_free_mb == 10240
        assert info.driver_version == "535.129.03"
        assert info.vram_level == "green"

    def test_rtx_4090(self):
        csv = "NVIDIA GeForce RTX 4090, 24564, 23000, 546.01"
        info = parse_nvidia_smi_csv(csv)
        assert info.detected is True
        assert info.vram_total_mb == 24564
        assert info.vram_level == "green"

    def test_gtx_1060_6gb(self):
        csv = "NVIDIA GeForce GTX 1060, 6144, 5000, 470.82.01"
        info = parse_nvidia_smi_csv(csv)
        assert info.detected is True
        assert info.vram_level == "orange"

    def test_low_vram_2gb(self):
        csv = "NVIDIA GeForce GT 1030, 2048, 1800, 460.32"
        info = parse_nvidia_smi_csv(csv)
        assert info.vram_level == "red"

    def test_empty_string(self):
        info = parse_nvidia_smi_csv("")
        assert info.detected is False
        assert info.name is None

    def test_none_input(self):
        info = parse_nvidia_smi_csv("")
        assert info.detected is False

    def test_whitespace_only(self):
        info = parse_nvidia_smi_csv("   \n  ")
        assert info.detected is False

    def test_malformed_too_few_fields(self):
        info = parse_nvidia_smi_csv("NVIDIA, 12288")
        assert info.detected is False

    def test_malformed_non_numeric_vram(self):
        csv = "NVIDIA GeForce RTX 3060, abc, def, 535.129.03"
        info = parse_nvidia_smi_csv(csv)
        assert info.detected is True
        assert info.name == "NVIDIA GeForce RTX 3060"
        assert info.vram_total_mb is None
        assert info.vram_free_mb is None

    def test_multi_gpu_uses_first(self):
        csv = "NVIDIA GeForce RTX 3060, 12288, 10240, 535.129.03\nNVIDIA GeForce RTX 3070, 8192, 7000, 535.129.03"
        info = parse_nvidia_smi_csv(csv)
        assert info.name == "NVIDIA GeForce RTX 3060"
        assert info.vram_total_mb == 12288


# ─── CUDA version extraction ─────────────────────────────────────────────────

class TestExtractCudaVersion:
    def test_standard_header(self):
        header = """
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 535.129.03             Driver Version: 535.129.03   CUDA Version: 12.2       |
+-----------------------------------------------------------------------------------------+
"""
        assert extract_cuda_version(header) == "12.2"

    def test_cuda_11(self):
        header = "CUDA Version: 11.8"
        assert extract_cuda_version(header) == "11.8"

    def test_no_cuda(self):
        assert extract_cuda_version("no cuda info here") is None

    def test_empty(self):
        assert extract_cuda_version("") is None


# ─── query_gpu_info integration ───────────────────────────────────────────────

class TestQueryGpuInfo:
    def test_missing_nvidia_smi(self):
        with patch("gpu_utils.subprocess.run", side_effect=FileNotFoundError):
            info = query_gpu_info()
            assert info.detected is False
            assert info.vram_level == "red"

    def test_timeout(self):
        import subprocess
        with patch("gpu_utils.subprocess.run", side_effect=subprocess.TimeoutExpired("nvidia-smi", 5)):
            info = query_gpu_info()
            assert info.detected is False

    def test_successful_query(self):
        mock_csv = MagicMock()
        mock_csv.returncode = 0
        mock_csv.stdout = "NVIDIA GeForce RTX 3060, 12288, 10240, 535.129.03"

        mock_header = MagicMock()
        mock_header.returncode = 0
        mock_header.stdout = "CUDA Version: 12.2"

        with patch("gpu_utils.subprocess.run", side_effect=[mock_csv, mock_header]):
            info = query_gpu_info()
            assert info.detected is True
            assert info.name == "NVIDIA GeForce RTX 3060"
            assert info.cuda_version == "12.2"
            assert info.vram_level == "green"

    def test_nonzero_return_code(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("gpu_utils.subprocess.run", return_value=mock_result):
            info = query_gpu_info()
            assert info.detected is False


# ─── GPUInfo dataclass ────────────────────────────────────────────────────────

class TestGPUInfoDataclass:
    def test_to_dict(self):
        info = GPUInfo(detected=True, name="Test GPU", vram_total_mb=8192, vram_level="yellow")
        d = info.to_dict()
        assert d["detected"] is True
        assert d["name"] == "Test GPU"
        assert d["vram_total_mb"] == 8192
        assert d["vram_level"] == "yellow"

    def test_defaults(self):
        info = GPUInfo()
        assert info.detected is False
        assert info.name is None
        assert info.vram_level == "red"
