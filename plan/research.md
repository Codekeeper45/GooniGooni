# Modal GPU Reliability Research

Date: 2026-02-27

## Scope

This note covers operational limits and reliability controls in:

- `backend/config.py`
- `backend/app.py`
- `backend/api.py` (runtime orchestration needed for queue/fallback behavior)
- `backend/models/*`
- `backend/storage.py`
- `backend/tests/*` (policy coverage and current guarantees)

## What Exists Today (Evidence)

- Video and image function timeouts are `900s` and `300s` (`backend/config.py:58-59`, `backend/app.py:51-52`).
- Degraded video queue is bounded by `max_depth=25`, `max_wait=30s` (`backend/config.py:68-69`, `backend/api.py:243-252`).
- API marks queued tasks as failed after `120s` by default (`backend/api.py:570-575`).
- API endpoints are highly concurrent (`@modal.concurrent(max_inputs=50)`) with up to 3 API containers (`backend/app.py:725-727`, `backend/app.py:744-746`).
- GPU lanes are split across dedicated and degraded functions with independent `max_containers` (`backend/app.py:419-421`, `451`, `481`, `645-646`, `666`, `686`).
- Degraded queue admission in SQLite is currently count-then-insert (`backend/storage.py:618-632`).
- Operational snapshot is minimal: queue depth + 3 counters (`backend/storage.py:682-704`).
- Video degraded mode already protects VRAM on cross-model switch (`backend/app.py:161-165`, `backend/models/anisora.py:68-70`, `backend/models/phr00t.py:63-65`).
- Pony has local retry logic (3 attempts with safe fallback preset) (`backend/models/pony.py:183-236`).
- Existing tests validate defaults and basic queue/fallback counters (`backend/tests/test_config.py:121`, `158-168`; `backend/tests/test_queue_policy.py`; `backend/tests/test_video_lanes.py`; `backend/tests/test_api.py:160`, `233-244`).

## Decisions

## 1) Timeout Policy

Use layered timeouts with explicit ownership:

- Queue admission timeout: fast rejection of overloaded degraded lane.
- Worker pickup timeout: detect stuck scheduling, not long inference.
- Function timeout: hard ceiling for model execution.
- Stale cleanup timeout: final safety net.

Recommended defaults:

- `VIDEO_TIMEOUT=1200` (was 900)
- `IMAGE_TIMEOUT=420` (was 300)
- `VIDEO_DEGRADED_QUEUE_MAX_WAIT_SECONDS=20` (was 30)
- `VIDEO_DEGRADED_QUEUE_MAX_DEPTH=8` (was 25)
- `PENDING_WORKER_START_WARNING_SECONDS=90`
- `PENDING_WORKER_START_FAIL_SECONDS=300` (was 120)
- `STALE_TASK_HOURS=1` (was 2)

Rationale:

- `120s` worker-start failure is too aggressive for cold starts and causes false failures before pickup.
- `depth=25` with `VIDEO_CONCURRENCY=1` creates long queues that mostly end in user-visible latency, not throughput.
- Pony can run up to 3 decode attempts; `300s` is tight when retries happen under load.

Required code updates:

- Wire timeout values through one source (`config.py`) and consume from runtime modules instead of repeated `os.environ.get(...)`.
- Keep worker-start timeout separate from model runtime timeout; do not reuse function timeout for queue diagnostics.

## 2) Concurrency Policy

Primary goal: prevent hidden GPU overcommit from independent lane functions.

Recommended limits (single-account baseline):

- `VIDEO_CONCURRENCY=1`
- `IMAGE_CONCURRENCY=1`
- `VIDEO_ANISORA_MAX_CONTAINERS=1`
- `VIDEO_PHR00T_MAX_CONTAINERS=1`
- `IMAGE_PONY_MAX_CONTAINERS=1`
- `IMAGE_FLUX_MAX_CONTAINERS=1`
- API: `@modal.concurrent(max_inputs=20)` (was 50)

Additionally add global active-task caps across functions:

- `VIDEO_GLOBAL_ACTIVE_LIMIT=2`
- `IMAGE_GLOBAL_ACTIVE_LIMIT=2`

Implementation detail:

- Add a small lease table (`gpu_leases`) in storage.
- Acquire lease before spawning GPU work, release in `finally`.
- Reject with `503` + retry hint when global cap is reached.

Queue reliability fix:

- Make degraded queue admission atomic with `BEGIN IMMEDIATE` transaction in `try_admit_degraded_task`.
- This removes race windows from count-then-insert behavior under burst traffic.

## 3) Observability Policy

Current counters are useful but not enough for operations.

Add structured metrics/events:

- Per-task durations:
  - `queue_wait_seconds`
  - `worker_pickup_seconds`
  - `pipeline_load_seconds`
  - `inference_seconds`
  - `artifact_write_seconds`
  - `total_runtime_seconds`
- Failure taxonomy:
  - `failure_class` (`capacity`, `timeout`, `config`, `auth`, `quota`, `runtime`)
  - `failure_stage` (`queue`, `spawn`, `load`, `inference`, `artifact`)
- Capacity gauges:
  - active leases by modality
  - dedicated-lane spawn failures (rolling 5m)
  - fallback activation rate (rolling 5m)

API surface additions:

- Extend `/admin/health` diagnostics with rolling p50/p95 durations and failure rates.
- Add `/admin/metrics` endpoint for machine-readable snapshots (for dashboards/alerts).

Logging standard:

- Every operational event must include `task_id`, `model`, `lane_mode`, `event_type`, and monotonic timestamp.
- Emit one terminal event per task (`task_done` or `task_failed`) with classification and duration.

## 4) Fallback Policy

Adopt explicit fallback decision matrix:

- Dedicated lane spawn error `capacity|timeout|container_failed` -> fallback to degraded lane.
- Dedicated lane spawn error `config|auth|quota|manual_only` -> do not fallback silently; fail fast with actionable error.
- Degraded queue full (`depth >= max_depth`) -> `503 queue_overloaded` + metadata + retry hint.
- Degraded queue wait exceeded (`wait > max_wait`) -> `503 queue_timeout` + metadata.
- Remote account routing:
  - keep fallback across accounts for retryable upstream errors (already covered by router/admin tests),
  - no fallback on validation errors (`422`).

Add circuit breaker for dedicated lanes:

- If a model lane has >=3 spawn failures in 5 minutes, bypass dedicated lane for 2 minutes and send directly to degraded mode.
- Record `fallback_reason="circuit_open"` for observability and postmortem clarity.

## Test Plan Updates

Extend existing suites with policy-level assertions:

- `test_config.py`: new defaults and env override checks for added timeout/concurrency knobs.
- `test_queue_policy.py`: atomic admission under concurrent inserts (race test).
- `test_video_lanes.py`: verify `queue_timeout` and `circuit_open` counters.
- `test_api.py`:
  - verify worker-start timeout no longer fails healthy cold start paths,
  - verify `503 queue_timeout` contract,
  - verify diagnostics include new duration/failure fields.
- `test_storage.py`: lease acquire/release lifecycle and snapshot aggregation.

## Rollout Plan

- Phase 1: ship observability fields first (no behavioral risk).
- Phase 2: apply queue atomicity + timeout default changes.
- Phase 3: enable global lease caps and dedicated-lane circuit breaker.
- Phase 4: tighten limits based on real p95 metrics after 48h traffic.

Success criteria after rollout:

- `worker_start_timeout` false positives reduced to near zero.
- `queue_overloaded` becomes short-burst signal, not steady-state.
- p95 time-to-first-processing stable and visible in admin diagnostics.
- fallback events are classified and actionable, not generic.
