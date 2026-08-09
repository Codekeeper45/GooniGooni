"""Shared model contract and runtime configuration tests."""
import importlib
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config


def test_only_pony_is_exposed():
    assert len(config.MODELS_SCHEMA) == 1
    model = config.MODELS_SCHEMA[0]
    assert model["id"] == "pony"
    assert model["type"] == "image"
    assert model["modes"] == ["txt2img", "img2img"]


def test_contract_is_valid_json_and_versioned():
    contract = json.loads((BACKEND_DIR / "pony_contract.json").read_text())
    assert contract["version"] == 1
    assert contract == config.PONY_CONTRACT


def test_frontend_imports_the_same_contract():
    frontend_api = (BACKEND_DIR.parent / "src/app/api.ts").read_text()
    assert 'import ponyContract from "../../backend/pony_contract.json"' in frontend_api
    assert "export const PONY_CONTRACT = ponyContract" in frontend_api


def test_pytorch_package_versions_match():
    requirements = (BACKEND_DIR / "requirements.txt").read_text()
    app_source = (BACKEND_DIR / "app.py").read_text()
    for requirement in (
        "torch==2.4.0",
        "torchvision==0.19.0",
        "diffusers==0.32.2",
        "torchsde==0.2.6",
    ):
        assert requirement in requirements
        assert f'"{requirement}"' in app_source


def test_model_id_can_be_overridden(monkeypatch):
    monkeypatch.setenv("PONY_MODEL_ID", "custom/pony")
    reloaded = importlib.reload(config)
    assert reloaded.PONY_MODEL_ID == "custom/pony"
    monkeypatch.delenv("PONY_MODEL_ID")
    importlib.reload(config)
