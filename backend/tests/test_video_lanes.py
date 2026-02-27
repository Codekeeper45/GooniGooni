"""
Unit tests for dedicated/degraded video lane support primitives.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    import config
    import storage

    db_file = str(tmp_path / "test_lanes.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "RESULTS_PATH", str(tmp_path))
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    monkeypatch.setattr(storage, "RESULTS_PATH", str(tmp_path))
    storage.init_db()


def test_video_lane_constants_have_expected_defaults():
    import config

    assert config.DEGRADED_QUEUE_MAX_DEPTH == 25
    assert config.DEGRADED_QUEUE_MAX_WAIT_SECONDS == 30
    assert config.DEGRADED_QUEUE_OVERLOAD_CODE == "queue_overloaded"


def test_operational_event_roundtrip():
    import storage

    storage.record_operational_event(
        "fallback_activated",
        task_id="task-1",
        model="anisora",
        lane_mode="degraded_shared",
        reason="capacity",
    )
    events = storage.list_operational_events(limit=10)
    assert len(events) == 1
    assert events[0]["event_type"] == "fallback_activated"
    assert events[0]["reason"] == "capacity"


def test_operational_snapshot_counts():
    import storage

    storage.record_operational_event("queue_overloaded", task_id="task-1")
    storage.record_operational_event("queue_timeout", task_id="task-2")
    storage.record_operational_event("fallback_activated", task_id="task-3")
    storage.record_operational_event("fallback_success", task_id="task-4")
    storage.record_operational_event("pipeline_cache_hit", task_id="task-5")
    storage.record_operational_event("pipeline_cache_miss", task_id="task-6")
    snap = storage.get_operational_snapshot()
    assert snap["queue_overloaded_count"] == 1
    assert snap["queue_timeout_count"] == 1
    assert snap["fallback_count"] == 1
    assert snap["fallback_success_count"] == 1
    assert snap["pipeline_cache_hit_count"] == 1
    assert snap["pipeline_cache_miss_count"] == 1
    assert "sc_metrics_24h" in snap
    assert isinstance(snap["sc_metrics_24h"], dict)


def test_cache_guardrails_prevent_redundant_anisora_load_same_cache_path():
    from models.anisora import AnisoraPipeline

    pipe = AnisoraPipeline("hf/repo")
    assert pipe._is_loaded_for_cache("/cache/a") is False

    pipe.load("/cache/a")
    first_count = getattr(pipe, "_full_load_count", 0)
    assert first_count == 1
    assert pipe._is_loaded_for_cache("/cache/a") is True

    pipe.load("/cache/a")
    second_count = getattr(pipe, "_full_load_count", 0)
    assert second_count == first_count

    pipe.load("/cache/b")
    third_count = getattr(pipe, "_full_load_count", 0)
    assert third_count == first_count + 1
    assert pipe._is_loaded_for_cache("/cache/b") is True


def test_oom_mapping_returns_structured_gpu_code_for_worker_errors():
    import app as backend_app

    oom_msg, stage_detail = backend_app._map_worker_error(
        RuntimeError("CUDA out of memory. Tried to allocate 50.00 MiB"),
        "A10G",
    )
    assert "gpu_memory_exceeded" in oom_msg
    assert "A10G" in oom_msg
    assert stage_detail == "gpu_oom"

    plain_msg, plain_stage = backend_app._map_worker_error(RuntimeError("network timeout"), "A10G")
    assert plain_msg == "network timeout"
    assert plain_stage == "RuntimeError"


def test_vram_budget_exceeded_event_hook_exists_in_worker_finalizers():
    import app as backend_app

    video_src = inspect.getsource(backend_app._execute_video_generation)
    image_src = inspect.getsource(backend_app._execute_image_generation)
    assert "vram_budget_exceeded" in video_src
    assert "vram_budget_exceeded" in image_src
