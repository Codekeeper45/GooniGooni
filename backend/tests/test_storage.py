"""
Unit tests for backend/storage.py
Uses a temporary SQLite database — no GPU, no Modal, no real files.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND = str(Path(__file__).parent.parent)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect DB_PATH to a temp file for every test."""
    db_file = str(tmp_path / "test_gallery.db")
    monkeypatch.setenv("RESULTS_PATH", str(tmp_path))

    import config
    monkeypatch.setattr(config, "DB_PATH", db_file)
    monkeypatch.setattr(config, "RESULTS_PATH", str(tmp_path))

    import storage
    # Re-patch the module-level constants storage uses
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    monkeypatch.setattr(storage, "RESULTS_PATH", str(tmp_path))
    storage.init_db()
    yield tmp_path


import storage  # noqa: E402 (after fixture definition)


# ─── create_task ─────────────────────────────────────────────────────────────

class TestCreateTask:
    def test_returns_uuid_string(self):
        task_id = storage.create_task(
            model="pony", gen_type="image", mode="txt2img",
            prompt="test", negative_prompt="", parameters={},
            width=512, height=512, seed=-1,
        )
        assert isinstance(task_id, str)
        assert len(task_id) == 36  # UUID-4 format

    def test_creates_pending_status(self):
        task_id = storage.create_task(
            model="pony", gen_type="image", mode="txt2img",
            prompt="test", negative_prompt="", parameters={},
            width=512, height=512, seed=-1,
        )
        result = storage.get_task(task_id)
        assert result is not None
        assert result.status.value == "pending"
        assert result.progress == 0

    def test_stores_all_fields(self):
        task_id = storage.create_task(
            model="flux", gen_type="image", mode="img2img",
            prompt="hello world", negative_prompt="bad quality",
            parameters={"steps": 25}, width=1024, height=768, seed=42,
        )
        result = storage.get_task(task_id)
        assert result.task_id == task_id


# ─── update_task_status ───────────────────────────────────────────────────────

class TestUpdateTaskStatus:
    def _make_task(self):
        return storage.create_task(
            model="pony", gen_type="image", mode="txt2img",
            prompt="test", negative_prompt="", parameters={},
            width=512, height=512, seed=0,
        )

    def test_update_to_processing(self):
        tid = self._make_task()
        storage.update_task_status(
            tid,
            "processing",
            progress=20,
            stage="loading_pipeline",
            stage_detail="model=anisora",
            lane_mode="dedicated",
        )
        result = storage.get_task(tid)
        assert result.status.value == "processing"
        assert result.progress == 20
        assert result.stage == "loading_pipeline"
        assert result.stage_detail == "model=anisora"
        assert result.lane_mode == "dedicated"

    def test_update_to_done_with_paths(self):
        tid = self._make_task()
        storage.update_task_status(
            tid, "done", progress=100,
            result_path="/results/abc/result.png",
            preview_path="/results/abc/preview.jpg",
        )
        result = storage.get_task(tid)
        assert result.status.value == "done"
        assert result.progress == 100

    def test_update_to_failed_with_error(self):
        tid = self._make_task()
        storage.update_task_status(tid, "failed", error_msg="CUDA OOM")
        result = storage.get_task(tid)
        assert result.status.value == "failed"
        assert result.error_msg == "CUDA OOM"

    def test_idempotent_update(self):
        tid = self._make_task()
        storage.update_task_status(tid, "processing", progress=50)
        storage.update_task_status(tid, "processing", progress=80)
        result = storage.get_task(tid)
        assert result.progress == 80


# ─── get_task ─────────────────────────────────────────────────────────────────

class TestGetTask:
    def test_returns_none_for_unknown_id(self):
        result = storage.get_task("nonexistent-id-xyz")
        assert result is None

    def test_returns_correct_task(self):
        tid1 = storage.create_task(
            model="anisora", gen_type="video", mode="t2v",
            prompt="video one", negative_prompt="", parameters={},
            width=720, height=1280, seed=1,
        )
        tid2 = storage.create_task(
            model="flux", gen_type="image", mode="txt2img",
            prompt="image two", negative_prompt="", parameters={},
            width=1024, height=1024, seed=2,
        )
        r1 = storage.get_task(tid1)
        r2 = storage.get_task(tid2)
        assert r1.task_id == tid1
        assert r2.task_id == tid2

    def test_urls_are_none_without_public_base_url(self, monkeypatch):
        monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
        tid = storage.create_task(
            model="pony", gen_type="image", mode="txt2img",
            prompt="url test", negative_prompt="", parameters={},
            width=512, height=512, seed=1,
        )
        storage.update_task_status(
            tid, "done", progress=100,
            result_path=f"/results/{tid}/result.png",
            preview_path=f"/results/{tid}/preview.jpg",
        )
        row = storage.get_task(tid)
        assert row.result_url is None
        assert row.preview_url is None

    def test_urls_are_absolute_with_public_base_url(self, monkeypatch):
        monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com/")
        tid = storage.create_task(
            model="pony", gen_type="image", mode="txt2img",
            prompt="url test", negative_prompt="", parameters={},
            width=512, height=512, seed=1,
        )
        storage.update_task_status(
            tid, "done", progress=100,
            result_path=f"/results/{tid}/result.png",
            preview_path=f"/results/{tid}/preview.jpg",
        )
        row = storage.get_task(tid)
        assert row.result_url == f"https://example.com/results/{tid}"
        assert row.preview_url == f"https://example.com/preview/{tid}"


# ─── list_gallery ─────────────────────────────────────────────────────────────

class TestListGallery:
    def _add_done_task(self, model="pony", gen_type="image"):
        tid = storage.create_task(
            model=model, gen_type=gen_type, mode="txt2img",
            prompt="gallery test", negative_prompt="", parameters={},
            width=512, height=512, seed=0,
        )
        storage.update_task_status(
            tid, "done", progress=100,
            result_path=f"/results/{tid}/result.png",
            preview_path=f"/results/{tid}/preview.jpg",
        )
        return tid

    def test_empty_gallery(self):
        items, total = storage.list_gallery()
        assert items == []
        assert total == 0

    def test_returns_done_tasks(self):
        self._add_done_task()
        items, total = storage.list_gallery()
        assert total == 1
        assert len(items) == 1

    def test_excludes_pending_tasks(self):
        storage.create_task(
            model="pony", gen_type="image", mode="txt2img",
            prompt="pending task", negative_prompt="", parameters={},
            width=512, height=512, seed=0,
        )
        items, total = storage.list_gallery()
        assert total == 0

    def test_pagination(self):
        for _ in range(5):
            self._add_done_task()
        items, total = storage.list_gallery(page=1, per_page=3)
        assert total == 5
        assert len(items) == 3

        items2, _ = storage.list_gallery(page=2, per_page=3)
        assert len(items2) == 2

    def test_model_filter(self):
        self._add_done_task(model="pony")
        self._add_done_task(model="flux", gen_type="image")
        items, total = storage.list_gallery(model_filter="pony")
        assert total == 1
        assert items[0].model == "pony"

    def test_type_filter(self):
        self._add_done_task(model="pony", gen_type="image")
        self._add_done_task(model="anisora", gen_type="video")
        items, total = storage.list_gallery(type_filter="video")
        assert total == 1
        assert items[0].type == "video"

    def test_gallery_urls_none_without_public_base_url(self, monkeypatch):
        monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
        self._add_done_task()
        items, _ = storage.list_gallery()
        assert items[0].result_url is None
        assert items[0].preview_url is None


# ─── delete_gallery_item ──────────────────────────────────────────────────────

class TestSessionAndRetentionHelpers:
    def test_count_active_tasks_for_session(self):
        session_token = "sess-1"

        t1 = storage.create_task(
            model="pony",
            gen_type="image",
            mode="txt2img",
            prompt="p1",
            negative_prompt="",
            parameters={},
            width=512,
            height=512,
            seed=1,
            generation_session_token=session_token,
        )
        storage.update_task_status(t1, "processing", progress=10)

        storage.create_task(
            model="flux",
            gen_type="image",
            mode="txt2img",
            prompt="p2",
            negative_prompt="",
            parameters={},
            width=512,
            height=512,
            seed=2,
            generation_session_token=session_token,
        )

        t3 = storage.create_task(
            model="pony",
            gen_type="image",
            mode="txt2img",
            prompt="p3",
            negative_prompt="",
            parameters={},
            width=512,
            height=512,
            seed=3,
            generation_session_token=session_token,
        )
        storage.update_task_status(t3, "done", progress=100)

        assert storage.count_active_tasks_for_session(session_token) == 2

    def test_cleanup_expired_artifacts_detaches_paths_and_deletes_files(self):
        tid = storage.create_task(
            model="pony",
            gen_type="image",
            mode="txt2img",
            prompt="expire",
            negative_prompt="",
            parameters={},
            width=512,
            height=512,
            seed=1,
            generation_session_token="sess-2",
            artifact_ttl_days=1,
        )

        result_path = Path(storage.result_file_path(tid, "png"))
        preview_path = Path(storage.preview_file_path(tid))
        result_path.write_bytes(b"fake-image")
        preview_path.write_bytes(b"fake-preview")

        storage.update_task_status(
            tid,
            "done",
            progress=100,
            result_path=str(result_path),
            preview_path=str(preview_path),
        )

        expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with storage._db() as conn:  # test-only access to storage context manager
            conn.execute(
                "UPDATE tasks SET artifact_expires_at=? WHERE id=?",
                (expired_at, tid),
            )

        cleaned = storage.cleanup_expired_artifacts(now=datetime.now(timezone.utc))
        assert cleaned == 1
        assert not result_path.exists()
        assert not preview_path.exists()

        raw = storage.get_raw_task(tid)
        assert raw is not None
        assert raw["result_path"] is None
        assert raw["preview_path"] is None

class TestDeleteGalleryItem:
    def test_delete_existing_task(self):
        tid = storage.create_task(
            model="pony", gen_type="image", mode="txt2img",
            prompt="delete test", negative_prompt="", parameters={},
            width=512, height=512, seed=0,
        )
        storage.update_task_status(
            tid, "done", progress=100,
            result_path=f"/results/{tid}/result.png",
        )
        deleted = storage.delete_gallery_item(tid)
        assert deleted is True
        assert storage.get_task(tid) is None

    def test_delete_nonexistent_task(self):
        deleted = storage.delete_gallery_item("does-not-exist")
        assert deleted is False


class TestDegradedQueueHelpers:
    def test_admit_and_release(self):
        admitted, depth = storage.try_admit_degraded_task("q1", max_depth=1)
        assert admitted is True
        assert depth == 1
        admitted, depth = storage.try_admit_degraded_task("q2", max_depth=1)
        assert admitted is False
        assert depth == 1
        storage.release_degraded_task("q1")
        assert storage.degraded_queue_size() == 0

    def test_operational_events_are_stored(self):
        storage.record_operational_event("queue_overloaded", task_id="q1", value=25)
        events = storage.list_operational_events(limit=5)
        assert len(events) == 1
        assert events[0]["event_type"] == "queue_overloaded"


class TestTerminalStateIntegrity:
    def test_done_state_keeps_artifact_paths_retrievable(self):
        tid = storage.create_task(
            model="pony",
            gen_type="image",
            mode="txt2img",
            prompt="terminal done",
            negative_prompt="",
            parameters={"steps": 20},
            width=512,
            height=512,
            seed=111,
        )
        result_path = storage.result_file_path(tid, "png")
        preview_path = storage.preview_file_path(tid)
        storage.update_task_status(
            tid,
            "done",
            progress=100,
            result_path=result_path,
            preview_path=preview_path,
            stage="done",
            stage_detail="artifact_write",
        )

        status_row = storage.get_task(tid)
        raw_row = storage.get_raw_task(tid)
        assert status_row is not None
        assert status_row.status.value == "done"
        assert status_row.progress == 100
        assert raw_row is not None
        assert raw_row["result_path"] == result_path
        assert raw_row["preview_path"] == preview_path

    def test_failed_state_preserves_error_without_artifact_paths(self):
        tid = storage.create_task(
            model="anisora",
            gen_type="video",
            mode="t2v",
            prompt="terminal failed",
            negative_prompt="",
            parameters={"steps": 8},
            width=512,
            height=512,
            seed=222,
        )
        storage.update_task_status(
            tid,
            "failed",
            progress=0,
            error_msg="Worker start timeout",
            stage="failed",
            stage_detail="worker_start_timeout",
        )

        status_row = storage.get_task(tid)
        raw_row = storage.get_raw_task(tid)
        assert status_row is not None
        assert status_row.status.value == "failed"
        assert status_row.error_msg == "Worker start timeout"
        assert raw_row is not None
        assert raw_row["result_path"] is None
        assert raw_row["preview_path"] is None


class TestSuccessCriteriaMetrics:
    def test_sc_metrics_aggregate_latency_fallback_and_resume(self):
        tid_done = storage.create_task(
            model="pony",
            gen_type="image",
            mode="txt2img",
            prompt="done",
            negative_prompt="",
            parameters={},
            width=512,
            height=512,
            seed=1,
        )
        tid_failed = storage.create_task(
            model="anisora",
            gen_type="video",
            mode="t2v",
            prompt="failed",
            negative_prompt="",
            parameters={},
            width=512,
            height=512,
            seed=2,
        )
        storage.update_task_status(tid_done, "done", progress=100)
        storage.update_task_status(tid_failed, "failed", error_msg="err")

        storage.record_operational_event("generation_accepted", task_id=tid_done, value=1.5)
        storage.record_operational_event("generation_accepted", task_id=tid_failed, value=2.5)
        storage.record_operational_event("status_freshness_seconds", task_id=tid_done, value=1.0)
        storage.record_operational_event("status_freshness_seconds", task_id=tid_failed, value=3.0)
        storage.record_operational_event("fallback_activated", task_id=tid_failed)
        storage.record_operational_event("fallback_success", task_id=tid_done)
        storage.record_operational_event("resume_attempt", task_id=tid_done)
        storage.record_operational_event("resume_success", task_id=tid_done)

        metrics = storage.get_sc_metrics(hours=24)
        assert metrics["total_tasks"] == 2
        assert metrics["terminal_tasks"] == 2
        assert metrics["terminal_rate"] == 1.0
        assert metrics["accept_latency_avg_seconds"] == 2.0
        assert metrics["accept_latency_samples"] == 2
        assert metrics["status_freshness_avg_seconds"] == 2.0
        assert metrics["status_freshness_samples"] == 2
        assert metrics["fallback_needed"] == 1
        assert metrics["fallback_success"] == 1
        assert metrics["fallback_success_rate"] == 1.0
        assert metrics["resume_attempts"] == 1
        assert metrics["resume_success"] == 1
        assert metrics["resume_success_rate"] == 1.0

    def test_sc_metrics_empty_window_returns_none_rates(self):
        metrics = storage.get_sc_metrics(hours=24)
        assert metrics["total_tasks"] == 0
        assert metrics["terminal_tasks"] == 0
        assert metrics["terminal_rate"] is None
        assert metrics["accept_latency_avg_seconds"] is None
        assert metrics["fallback_success_rate"] is None
        assert metrics["resume_success_rate"] is None

