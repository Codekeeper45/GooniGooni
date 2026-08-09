"""File-per-result storage tests; no SQLite and no Modal required."""
import json
import sys
import uuid
from pathlib import Path

import pytest

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import storage


@pytest.fixture(autouse=True)
def isolated_results(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ITEMS_PATH", str(tmp_path / "items"))
    return tmp_path


def request_payload(prompt="test"):
    return {
        "model": "pony",
        "type": "image",
        "mode": "txt2img",
        "prompt": prompt,
        "negative_prompt": "bad",
        "width": 1024,
        "height": 1024,
        "steps": 30,
        "cfg_scale": 6.0,
        "sampler": "Euler a",
        "clip_skip": 2,
        "denoising_strength": 0.7,
        "seed": -1,
        "output_format": "png",
        "reference_image": None,
    }


def create_complete_item(prompt="test"):
    result_id = str(uuid.uuid4())
    result = Path(storage.result_file_path(result_id, "png"))
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_bytes(b"png")
    Path(storage.preview_file_path(result_id)).write_bytes(b"jpg")
    storage.write_manifest(result_id, request_payload(prompt), 42)
    return result_id


def test_manifest_round_trip():
    result_id = create_complete_item("hello")
    manifest = storage.read_manifest(result_id)
    assert manifest["id"] == result_id
    assert manifest["prompt"] == "hello"
    assert manifest["seed"] == 42


def test_gallery_only_lists_complete_items():
    complete_id = create_complete_item()
    incomplete_id = str(uuid.uuid4())
    storage.write_manifest(incomplete_id, request_payload(), 1)
    items, total = storage.list_gallery(1, 24)
    assert total == 1
    assert items[0]["id"] == complete_id


def test_gallery_paginates_newest_first():
    ids = [create_complete_item(str(index)) for index in range(3)]
    for index, result_id in enumerate(ids):
        manifest_path = Path(storage.preview_file_path(result_id)).parent / "manifest.json"
        data = json.loads(manifest_path.read_text())
        data["created_at"] = f"2026-01-0{index + 1}T00:00:00+00:00"
        manifest_path.write_text(json.dumps(data))
    first, total = storage.list_gallery(1, 2)
    second, _ = storage.list_gallery(2, 2)
    assert total == 3
    assert [item["prompt"] for item in first] == ["2", "1"]
    assert [item["prompt"] for item in second] == ["0"]


def test_delete_removes_only_target_directory():
    first = create_complete_item("first")
    second = create_complete_item("second")
    assert storage.delete_gallery_item(first) is True
    assert storage.read_manifest(first) is None
    assert storage.read_manifest(second) is not None


@pytest.mark.parametrize("unsafe_id", ["../secret", "x", "a" * 36, ""])
def test_path_traversal_ids_are_rejected(unsafe_id):
    with pytest.raises(ValueError):
        storage.get_result_path(unsafe_id)
