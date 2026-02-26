"""
Unit tests for dedicated/degraded video lane support primitives.
"""
from __future__ import annotations

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
    snap = storage.get_operational_snapshot()
    assert snap["queue_overloaded_count"] == 1
    assert snap["queue_timeout_count"] == 1
    assert snap["fallback_count"] == 1
