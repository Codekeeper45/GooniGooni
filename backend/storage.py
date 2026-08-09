"""File-per-result storage.

Each generation owns a separate directory, so Modal containers never modify the
same file concurrently. Task execution state comes from Modal FunctionCall, not
from this volume.
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import ITEMS_PATH, MAX_PAGE_SIZE

def _validate_id(result_id: str) -> str:
    try:
        parsed = uuid.UUID(result_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError("Invalid result id") from exc
    if parsed.version != 4 or str(parsed) != result_id:
        raise ValueError("Invalid result id")
    return result_id


def _item_dir(result_id: str) -> Path:
    return Path(ITEMS_PATH) / _validate_id(result_id)


def result_file_path(result_id: str, output_format: str) -> str:
    extension = "jpg" if output_format == "jpeg" else "png"
    return str(_item_dir(result_id) / f"result.{extension}")


def preview_file_path(result_id: str) -> str:
    return str(_item_dir(result_id) / "preview.jpg")


def _manifest_path(result_id: str) -> Path:
    return _item_dir(result_id) / "manifest.json"


def write_manifest(
    result_id: str,
    request: dict[str, Any],
    resolved_seed: int,
    created_at: str | None = None,
) -> dict[str, Any]:
    item_dir = _item_dir(result_id)
    item_dir.mkdir(parents=True, exist_ok=True)
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": 1,
        "id": result_id,
        "model": "pony",
        "mode": request["mode"],
        "prompt": request["prompt"],
        "negative_prompt": request.get("negative_prompt", ""),
        "width": request["width"],
        "height": request["height"],
        "steps": request["steps"],
        "cfg_scale": request["cfg_scale"],
        "sampler": request["sampler"],
        "clip_skip": request["clip_skip"],
        "denoising_strength": request["denoising_strength"],
        "seed": resolved_seed,
        "output_format": request["output_format"],
        "created_at": created_at,
    }
    target = _manifest_path(result_id)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return manifest


def read_manifest(result_id: str) -> dict[str, Any] | None:
    path = _manifest_path(result_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_gallery(page: int, per_page: int) -> tuple[list[dict[str, Any]], int]:
    page = max(1, page)
    per_page = max(1, min(per_page, MAX_PAGE_SIZE))
    root = Path(ITEMS_PATH)
    if not root.exists():
        return [], 0

    items: list[dict[str, Any]] = []
    for manifest_path in root.glob("*/manifest.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            result_path = Path(result_file_path(data["id"], data["output_format"]))
            preview_path = Path(preview_file_path(data["id"]))
            if result_path.is_file() and preview_path.is_file():
                items.append(data)
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            continue

    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    total = len(items)
    offset = (page - 1) * per_page
    return items[offset : offset + per_page], total


def delete_gallery_item(result_id: str) -> bool:
    item_dir = _item_dir(result_id)
    if not item_dir.is_dir():
        return False
    shutil.rmtree(item_dir)
    return True


def get_result_path(result_id: str) -> str | None:
    manifest = read_manifest(result_id)
    if not manifest:
        return None
    path = result_file_path(result_id, manifest["output_format"])
    return path if os.path.isfile(path) else None


def get_preview_path(result_id: str) -> str | None:
    path = preview_file_path(result_id)
    return path if os.path.isfile(path) else None
