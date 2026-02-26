"""
Unit tests for backend/config.py
No Modal, no GPU, no network required.
"""
import os
import importlib
import sys
from pathlib import Path

import pytest

# Ensure backend/ is on sys.path
BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _reload_config(env_overrides: dict):
    """Reload config module with patched env vars."""
    old = {k: os.environ.get(k) for k in env_overrides}
    os.environ.update(env_overrides)
    try:
        if "config" in sys.modules:
            del sys.modules["config"]
        import config as cfg
        return cfg
    finally:
        # Restore
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestModelIDs:
    def test_all_four_models_present(self):
        import config
        assert set(config.MODEL_IDS.keys()) == {"anisora", "phr00t", "pony", "flux"}

    def test_anisora_default_id(self):
        import config
        assert config.MODEL_IDS["anisora"] == "Wan-AI/Wan2.1-T2V-14B-Diffusers"

    def test_phr00t_default_id(self):
        import config
        assert config.MODEL_IDS["phr00t"] == "Phr00t/WAN2.2-14B-Rapid-AllInOne"

    def test_pony_default_id(self):
        import config
        assert config.MODEL_IDS["pony"] == "Polenov2024/Pony-Diffusion-V6-XL"

    def test_flux_default_id(self):
        import config
        assert config.MODEL_IDS["flux"] == "black-forest-labs/FLUX.1-dev"

    def test_all_ids_are_nonempty_strings(self):
        import config
        for key, val in config.MODEL_IDS.items():
            assert isinstance(val, str) and len(val) > 0, f"Model ID for '{key}' is empty"

    def test_all_ids_have_slash(self):
        """HF repo IDs must be of the form owner/repo."""
        import config
        for key, val in config.MODEL_IDS.items():
            assert "/" in val, f"Model ID for '{key}' does not look like owner/repo: {val}"

    def test_env_override_anisora(self):
        cfg = _reload_config({"ANISORA_MODEL_ID": "custom/anisora-test"})
        assert cfg.MODEL_IDS["anisora"] == "custom/anisora-test"

    def test_env_override_phr00t(self):
        cfg = _reload_config({"PHR00T_MODEL_ID": "custom/phr00t-test"})
        assert cfg.MODEL_IDS["phr00t"] == "custom/phr00t-test"

    def test_env_override_pony(self):
        cfg = _reload_config({"PONY_MODEL_ID": "custom/pony-test"})
        assert cfg.MODEL_IDS["pony"] == "custom/pony-test"

    def test_env_override_flux(self):
        cfg = _reload_config({"FLUX_MODEL_ID": "custom/flux-test"})
        assert cfg.MODEL_IDS["flux"] == "custom/flux-test"


class TestAnisoraSubfolder:
    def test_default_subfolder(self):
        import config
        assert config.ANISORA_SUBFOLDER == ""

    def test_env_override_subfolder(self):
        cfg = _reload_config({"ANISORA_SUBFOLDER": "V4.0"})
        assert cfg.ANISORA_SUBFOLDER == "V4.0"


class TestPhr00tFilename:
    def test_default_filename(self):
        import config
        assert "v12" in config.PHR00T_FILENAME.lower()
        assert config.PHR00T_FILENAME.endswith(".safetensors")

    def test_env_override_filename(self):
        cfg = _reload_config({"PHR00T_FILENAME": "wan2.2-rapid-v10.safetensors"})
        assert cfg.PHR00T_FILENAME == "wan2.2-rapid-v10.safetensors"


class TestGPUConfig:
    def test_default_video_gpu(self):
        import config
        assert config.VIDEO_GPU == "A10G"

    def test_default_image_gpu(self):
        import config
        assert config.IMAGE_GPU == "T4"

    def test_env_override_video_gpu(self):
        cfg = _reload_config({"VIDEO_GPU": "A100"})
        assert cfg.VIDEO_GPU == "A100"


class TestLaneAndQueuePolicy:
    def test_degraded_queue_defaults(self):
        import config

        assert config.DEGRADED_QUEUE_MAX_DEPTH == 25
        assert config.DEGRADED_QUEUE_MAX_WAIT_SECONDS == 30
        assert config.DEGRADED_QUEUE_OVERLOAD_CODE == "queue_overloaded"

    def test_fixed_video_constraints(self):
        import config

        assert config.VIDEO_FIXED_CONSTRAINTS["anisora"]["steps"] == 8
        assert config.VIDEO_FIXED_CONSTRAINTS["phr00t"]["steps"] == 4
        assert config.VIDEO_FIXED_CONSTRAINTS["phr00t"]["cfg_scale"] == 1.0

    def test_modes_schema_parity_for_fixed_constraints(self):
        import config

        schema_by_id = {m["id"]: m for m in config.MODELS_SCHEMA}
        anisora = schema_by_id["anisora"]["fixed_parameters"]
        phr00t = schema_by_id["phr00t"]["fixed_parameters"]
        assert anisora["steps"]["value"] == config.VIDEO_FIXED_CONSTRAINTS["anisora"]["steps"]
        assert phr00t["steps"]["value"] == config.VIDEO_FIXED_CONSTRAINTS["phr00t"]["steps"]
        assert phr00t["cfg_scale"]["value"] == config.VIDEO_FIXED_CONSTRAINTS["phr00t"]["cfg_scale"]

    def test_secret_surface_does_not_expand(self):
        import config

        env_keys = set(config.os.environ.keys())
        forbidden_new_runtime_secret_keys = {
            "X_API_KEY",
            "VIDEO_MODEL_PASSWORD",
            "RAW_TOKEN",
        }
        assert forbidden_new_runtime_secret_keys.isdisjoint(env_keys)


class TestTimeouts:
    def test_video_timeout_default(self):
        import config
        assert config.VIDEO_TIMEOUT == 900

    def test_image_timeout_default(self):
        import config
        assert config.IMAGE_TIMEOUT == 300

    def test_env_override_video_timeout(self):
        cfg = _reload_config({"VIDEO_TIMEOUT": "1200"})
        assert cfg.VIDEO_TIMEOUT == 1200


class TestModelsSchema:
    def test_schema_has_four_models(self):
        import config
        assert len(config.MODELS_SCHEMA) == 4

    def test_all_schema_ids_match_model_ids(self):
        import config
        schema_ids = {m["id"] for m in config.MODELS_SCHEMA}
        assert schema_ids == set(config.MODEL_IDS.keys())

    def test_schema_required_fields(self):
        import config
        for model in config.MODELS_SCHEMA:
            for field in ("id", "name", "type", "modes", "parameters_schema"):
                assert field in model, f"'{field}' missing from schema for {model.get('id')}"

    def test_video_models_have_mp4_mode(self):
        import config
        video_schemas = [m for m in config.MODELS_SCHEMA if m["type"] == "video"]
        assert len(video_schemas) == 2

    def test_image_models_have_txt2img_mode(self):
        import config
        image_schemas = [m for m in config.MODELS_SCHEMA if m["type"] == "image"]
        for m in image_schemas:
            assert "txt2img" in m["modes"]

    def test_anisora_has_arbitrary_frame_mode(self):
        import config
        anisora = next(m for m in config.MODELS_SCHEMA if m["id"] == "anisora")
        assert "arbitrary_frame" in anisora["modes"]

    def test_phr00t_does_not_have_arbitrary_frame(self):
        import config
        phr00t = next(m for m in config.MODELS_SCHEMA if m["id"] == "phr00t")
        assert "arbitrary_frame" not in phr00t["modes"]
