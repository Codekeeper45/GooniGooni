# Implementation Plan: VRAM OOM Stability for Video Pipelines

**Branch**: `001-fix-vram-oom` | **Date**: 2026-02-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-fix-vram-oom/spec.md`

## Summary

Implement production-safe VRAM stability for heavy video generation by introducing model-dedicated warm execution lanes for AniSora and Phr00t, explicit degraded-mode routing with bounded queue controls, strict fixed-parameter validation for video requests, and mandatory memory observability. The plan prioritizes eliminating cross-model VRAM contention without sacrificing availability when dedicated capacity is constrained.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript + React 18 (frontend)  
**Primary Dependencies**: FastAPI, Modal, Pydantic v2, Diffusers/Wan pipelines, PyTorch 2.4.0, Vite  
**Storage**: Modal Volume `results`, Modal Volume `model-cache`, SQLite (`gallery.db`)  
**Testing**: `pytest backend/tests/`, targeted API regressions, frontend build `npm run build`, mandatory live smoke against deployed endpoint for real inference flow changes  
**Target Platform**: Modal GPU workers (A10G baseline for acceptance/performance gates; T4 supported with no p95 guarantee), Modal API app, GCP VM frontend  
**Project Type**: Web application (frontend + backend + admin)  
**Performance Goals**: (A10G baseline) warm model-switch task acceptance p95 < 3s; degraded wait timeout <= 30s; degraded queue depth <= 25  
**Constraints**: A10G VRAM ~24GB, heavy dual-model residency causes OOM, cold starts expensive, existing API/auth contracts must remain stable except explicit validation/overload responses  
**Scale/Scope**: Heavy video models `anisora` and `phr00t` only; image models unaffected; production fallback under capacity/quota pressure

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Contract + Config Integrity**: Contract changes (`422`, `503 queue_overloaded`) are mapped and `inference_settings.json` parity requirements are explicit.
- [x] **Modal Reliability**: Dedicated warm lanes, degraded fallback, VRAM constraints, timeout and queue controls are explicit.
- [x] **Auth + Secrets Safety**: Auth/cors/secret behavior remains unchanged; no new secret surfaces introduced.
- [x] **Storage Consistency**: Task lifecycle and fallback/queue state implications are documented for persistent observability.
- [x] **Test + Transparency Gates**: Required tests for OOM prevention, fixed-parameter validation, queue overload behavior, and memory logs are defined.

## Project Structure

### Documentation (this feature)

```text
specs/001-fix-vram-oom/
+-- plan.md
+-- research.md
+-- data-model.md
+-- quickstart.md
+-- contracts/
¦   L-- http-api.md
L-- tasks.md
```

### Source Code (repository root)

```text
backend/
+-- app.py
+-- config.py
+-- schemas.py
+-- storage.py
+-- router.py
+-- models/
¦   +-- base.py
¦   +-- anisora.py
¦   L-- phr00t.py
L-- tests/

src/
+-- inference_settings.json
L-- app/
    +-- components/
    ¦   +-- MediaGenApp.tsx
    ¦   L-- ControlPanel.tsx
    L-- utils/
        L-- configManager.ts
```

**Structure Decision**: Keep existing monorepo layout; implement backend lane split and degraded queue handling in `backend/app.py` + schema/config alignment, with companion frontend parity checks only where contract feedback is surfaced.

## Phase 0: Research Outcomes

1. Lane isolation strategy:
   - Split heavy video generation into model-dedicated execution lanes/functions.
   - Keep warm per-model lane in production profile when capacity allows.
   - Preserve safe degraded shared-worker path under quota/capacity pressure.
2. Queue control strategy:
   - Degraded mode uses bounded queue depth 25 and max wait 30s.
   - Exceeding limits returns deterministic `503 queue_overloaded`.
3. Parameter enforcement strategy:
   - AniSora video: fixed `steps=8`.
   - Phr00t video: fixed `steps=4`, `cfg=1.0`.
   - Violations fail pre-inference with `422`.
4. Memory safety strategy:
   - GPU workers set allocator anti-fragmentation env (`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`).
   - Memory cleanup and memory metrics logging required after generation paths.

Resolved in: [research.md](./research.md)

## Phase 1: Design & Contracts

1. Define lane/queue/constraint entities and state transitions in [data-model.md](./data-model.md).
2. Define API behavior deltas in [contracts/http-api.md](./contracts/http-api.md).
3. Define validation and rollout procedure in [quickstart.md](./quickstart.md).
4. Update AI agent context via `.specify/scripts/powershell/update-agent-context.ps1 -AgentType codex`.

## Phase 2: Planning Approach (Stop Point)

Next command (`/speckit.tasks`) will generate executable tasks for:
- dedicated video lane split and routing,
- degraded queue and overload contract,
- fixed parameter schema enforcement,
- memory cleanup/logging instrumentation,
- regression/perf tests and rollout verification.

## Post-Design Constitution Check (Re-evaluated)

- [x] **Contract + Config Integrity**: Contract deltas and config parity impacts are codified in contracts + data model.
- [x] **Modal Reliability**: Dedicated lane and degraded fallback behavior are concrete and testable.
- [x] **Auth + Secrets Safety**: No auth model weakening, no new secret paths.
- [x] **Storage Consistency**: Queue/fallback observability and task lifecycle handling are explicitly modeled.
- [x] **Test + Transparency Gates**: Gate tests and memory/queue diagnostics are explicit in quickstart.

## Complexity Tracking

No constitution violations requiring exception.

