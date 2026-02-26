"""
Unit tests for degraded queue admission policy.
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

    db_file = str(tmp_path / "test_queue.db")
    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "RESULTS_PATH", str(tmp_path))
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    monkeypatch.setattr(storage, "RESULTS_PATH", str(tmp_path))
    storage.init_db()


def test_degraded_queue_admission_respects_depth_limit():
    import storage

    admitted, depth = storage.try_admit_degraded_task("t1", max_depth=2)
    assert admitted is True
    assert depth == 1

    admitted, depth = storage.try_admit_degraded_task("t2", max_depth=2)
    assert admitted is True
    assert depth == 2

    admitted, depth = storage.try_admit_degraded_task("t3", max_depth=2)
    assert admitted is False
    assert depth == 2


def test_release_degraded_slot_frees_capacity():
    import storage

    storage.try_admit_degraded_task("t1", max_depth=1)
    admitted, _ = storage.try_admit_degraded_task("t2", max_depth=1)
    assert admitted is False

    storage.release_degraded_task("t1")
    admitted, depth = storage.try_admit_degraded_task("t2", max_depth=1)
    assert admitted is True
    assert depth == 1
