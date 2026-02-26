# Tasks: VRAM OOM Stability for Video Pipelines

**Input**: Design documents from `/specs/001-fix-vram-oom/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/http-api.md, quickstart.md

**Tests**: Include test tasks because this feature changes backend API behavior, inference routing, queue policy, and production observability.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)
- Every task includes an explicit file path

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare docs/config baseline and test scaffolding.

- [X] T001 Sync feature implementation checklist and rollout notes in `specs/001-fix-vram-oom/quickstart.md`
- [X] T002 [P] Sync API delta notes for fixed params and overload response in `specs/001-fix-vram-oom/contracts/http-api.md`
- [X] T003 [P] Add environment variable placeholders for lane/queue controls in `.env.example`
- [X] T004 Prepare lane/queue pytest fixture scaffolding in `backend/tests/conftest.py`
- [X] T005 [P] Create dedicated test module shell for lane routing in `backend/tests/test_video_lanes.py`
- [X] T006 [P] Create dedicated test module shell for degraded queue policy in `backend/tests/test_queue_policy.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core reliability and contract foundations required by all stories.

- [X] T007 Define lane and degraded queue constants in `backend/config.py`
- [X] T008 Add machine-readable overload/validation response models in `backend/schemas.py`
- [X] T009 Implement shared queue state helpers for degraded mode in `backend/storage.py`
- [X] T010 Add GPU allocator anti-fragmentation env defaults for video workers in `backend/app.py`
- [X] T011 Implement reusable memory cleanup utility for GPU pipelines in `backend/models/base.py`
- [X] T012 [P] Update fixed parameter source-of-truth entries for AniSora/Phr00t in `src/inference_settings.json`
- [X] T013 [P] Update payload builder to respect locked fixed parameters in `src/app/utils/configManager.ts`
- [X] T014 Add foundational schema regression tests for fixed parameter policy in `backend/tests/test_schemas.py`
- [X] T015 Add foundational API error-envelope regression tests in `backend/tests/test_api.py`
- [X] T016 Add config/source-of-truth parity regression tests in `backend/tests/test_config.py`

**Checkpoint**: Foundational rules are in place; user stories can proceed independently.

---

## Phase 3: User Story 1 - Stable Video Model Switching (Priority: P1) MVP

**Goal**: Prevent CUDA OOM during model switching by using dedicated warm lanes with safe degraded fallback.

**Independent Test**: Alternate AniSora and Phr00t generation requests and verify zero CUDA OOM, deterministic fallback behavior, and deterministic overload errors.

### Tests for User Story 1

- [X] T017 [P] [US1] Implement dedicated-lane routing unit tests in `backend/tests/test_video_lanes.py`
- [X] T018 [P] [US1] Implement degraded queue depth/wait admission tests in `backend/tests/test_queue_policy.py`
- [X] T019 [US1] Add API integration tests for `503 queue_overloaded` in `backend/tests/test_api.py`

### Implementation for User Story 1

- [X] T020 [US1] Split video generation into model-dedicated Modal functions in `backend/app.py`
- [X] T021 [US1] Implement `/generate` model-to-lane dispatch in `backend/app.py`
- [X] T022 [US1] Implement degraded shared-worker fallback routing with cause tags in `backend/app.py`
- [X] T023 [US1] Enforce degraded queue depth=25 and wait timeout=30s admission logic in `backend/app.py`
- [X] T024 [US1] Return deterministic machine-readable `503 queue_overloaded` in `backend/app.py`
- [X] T025 [P] [US1] Implement AniSora cleanup only for degraded cross-model switches while preserving dedicated warm-lane reuse in `backend/models/anisora.py`
- [X] T026 [P] [US1] Implement Phr00t cleanup only for degraded cross-model switches while preserving dedicated warm-lane reuse in `backend/models/phr00t.py`
- [X] T027 [P] [US1] Persist fallback/queue state transitions for diagnostics in `backend/storage.py`
- [X] T028 [US1] Surface overload error handling in generation UI flow in `src/app/components/MediaGenApp.tsx`

**Checkpoint**: US1 delivers stable switching and overload handling without OOM regressions.

---

## Phase 4: User Story 2 - Deterministic Fixed Video Parameters (Priority: P2)

**Goal**: Reject unsupported video parameters pre-inference with deterministic validation behavior.

**Independent Test**: Requests violating AniSora/Phr00t fixed parameter policy consistently return 422 before queue/dispatch.

### Tests for User Story 2

- [X] T029 [P] [US2] Add model-specific schema validation tests for AniSora/Phr00t in `backend/tests/test_schemas.py`
- [X] T030 [P] [US2] Add API contract tests for fixed-parameter `422` responses in `backend/tests/test_api.py`

### Implementation for User Story 2

- [X] T031 [US2] Implement model-specific fixed parameter validators in `backend/schemas.py`
- [X] T032 [US2] Normalize video parameter alias handling (`cfg`/`guidance_scale`) before validation in `backend/app.py`
- [X] T033 [P] [US2] Apply safe AniSora default fallback for optional `steps` input in `backend/models/anisora.py`
- [X] T034 [P] [US2] Align Phr00t runtime fixed values with schema constraints in `backend/models/phr00t.py`
- [X] T035 [US2] Remove hardcoded video fixed defaults from controls in `src/app/components/ControlPanel.tsx`
- [X] T036 [US2] Use config-driven pre-submit validation before generate request in `src/app/components/MediaGenApp.tsx`

**Checkpoint**: US2 enforces fixed parameters consistently across API, runtime, and UI behavior.

---

## Phase 5: User Story 3 - Operational Memory Safety Visibility (Priority: P3)

**Goal**: Provide operator-grade visibility into memory cleanup, fallback cause, and degraded queue behavior.

**Independent Test**: Logs/diagnostics show memory cleanup execution, lane readiness transitions, fallback causes, and queue overload metrics.

### Tests for User Story 3

- [X] T037 [P] [US3] Add memory cleanup and post-generation log assertions in `backend/tests/test_video_lanes.py`
- [X] T038 [P] [US3] Add fallback-cause and queue-metric assertions in `backend/tests/test_queue_policy.py`
- [X] T039 [US3] Add API/admin diagnostics visibility tests in `backend/tests/test_api.py`

### Implementation for User Story 3

- [X] T040 [US3] Add `finally`-path GPU cleanup and memory usage logging in `backend/app.py`
- [X] T041 [US3] Emit warm-lane readiness and cold-start events in `backend/app.py`
- [X] T042 [US3] Emit fallback activation reason and duration metrics in `backend/app.py`
- [X] T043 [US3] Emit degraded queue depth/wait/timeout/overload metrics in `backend/app.py`
- [X] T044 [P] [US3] Persist and query operational diagnostic events in `backend/storage.py`
- [X] T045 [P] [US3] Expose operational diagnostics through additive fields on existing admin/read responses in `backend/app.py`
- [X] T046 [US3] Surface operator diagnostics state in admin UI in `src/app/admin/AdminDashboard.tsx`

**Checkpoint**: US3 provides actionable production diagnostics for memory and queue safety.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final hardening, docs, and release gates.

- [X] T047 [P] Update public API integration guidance for fixed params and overload responses in `API_INTEGRATION_GUIDE.md`
- [X] T048 [P] Update RU operational testing guide with lane/queue scenarios in `TESTING_GUIDE_RU.md`
- [X] T049 [P] Update deployment/rollback notes for lane split and degraded mode in `README.md`
- [X] T050 Run full backend verification gate and record output in `specs/001-fix-vram-oom/quickstart.md`
- [X] T051 Run frontend build gate and record output in `specs/001-fix-vram-oom/quickstart.md`
- [ ] T052 Run targeted live smoke (switching + overload) and record evidence in `specs/001-fix-vram-oom/quickstart.md`
- [X] T053 [P] Add sensitive-log redaction regression tests for diagnostics in `backend/tests/test_api.py`
- [X] T054 Add lifecycle status visibility regression tests (`pending -> processing -> done|failed`) in `backend/tests/test_api.py`
- [X] T055 [P] Add capacity planning tradeoff and rollback trigger section in `README.md`
- [X] T056 [P] Add CORS/auth precedence non-regression tests in `backend/tests/test_auth.py`
- [X] T057 [P] Add secret-surface regression check (no new runtime secrets/env keys introduced) in `backend/tests/test_config.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6
- All user stories depend on completion of Phase 2 foundational work.
- Priority order remains US1 (MVP) -> US2 -> US3.

### User Story Dependency Graph

```text
Setup + Foundational
        |
       US1 (P1)
        |
       US2 (P2)
        |
       US3 (P3)
        |
      Polish
```

### Within Each User Story

- Tests first, then implementation tasks.
- Backend contract/schema changes before frontend integration tasks.
- Story checkpoint must pass before moving to the next priority story.

### Parallel Opportunities

- **US1**: T017 and T018 can run in parallel (different test modules); T025 and T026 can run in parallel (different model files).
- **US2**: T029 and T030 can run in parallel; T033 and T034 can run in parallel.
- **US3**: T037 and T038 can run in parallel; T044 and T045 can run in parallel.

---

## Implementation Strategy

### MVP First (US1)

1. Complete Setup + Foundational phases.
2. Deliver dedicated-lane split and degraded queue handling.
3. Validate zero OOM regressions and deterministic `503 queue_overloaded` behavior.

### Incremental Delivery

1. Add strict fixed-parameter enforcement (US2).
2. Add full operational diagnostics and admin visibility (US3).
3. Finish with cross-cutting docs and gate evidence.

### Gate Criteria Before Merge

- `pytest backend/tests/` passes.
- `npm run build` passes.
- Targeted switching/overload smoke evidence is recorded in quickstart.
- Contract/config parity for fixed parameters is verified.

