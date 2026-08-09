"""Dependency-light checks runnable in constrained development environments."""
from __future__ import annotations

import json
import sys
import tempfile
import uuid
from pathlib import Path

BACKEND = Path(__file__).parent.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

import config
import storage
from pydantic import ValidationError
from schemas import GenerateRequest


def check_contract() -> None:
    contract = json.loads((BACKEND / "pony_contract.json").read_text())
    assert contract == config.PONY_CONTRACT
    assert [model["id"] for model in config.MODELS_SCHEMA] == ["pony"]
    frontend = (ROOT / "src/app/api.ts").read_text()
    assert 'import ponyContract from "../../backend/pony_contract.json"' in frontend


def check_schema() -> None:
    request = GenerateRequest(prompt=" test ")
    assert request.prompt == "test"
    assert request.width == config.PONY_CONTRACT["defaults"]["width"]
    try:
        GenerateRequest(prompt="test", type="video")
    except ValidationError:
        pass
    else:
        raise AssertionError("Video payload must be rejected")
    try:
        GenerateRequest(prompt="test", extra_button="ignored")
    except ValidationError:
        pass
    else:
        raise AssertionError("Unknown UI fields must be rejected")


def check_storage() -> None:
    with tempfile.TemporaryDirectory() as directory:
        storage.ITEMS_PATH = str(Path(directory) / "items")
        result_id = str(uuid.uuid4())
        request = GenerateRequest(prompt="storage test").model_dump()
        result_path = Path(storage.result_file_path(result_id, "png"))
        result_path.parent.mkdir(parents=True)
        result_path.write_bytes(b"png")
        Path(storage.preview_file_path(result_id)).write_bytes(b"jpg")
        storage.write_manifest(result_id, request, 42)
        items, total = storage.list_gallery(1, 10)
        assert total == 1 and items[0]["seed"] == 42
        assert storage.delete_gallery_item(result_id)
        assert storage.read_manifest(result_id) is None


if __name__ == "__main__":
    check_contract()
    check_schema()
    check_storage()
    print("contract checks: OK")
