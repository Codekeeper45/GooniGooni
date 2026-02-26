# Tasks: MUST Inference Platform Baseline

**Input**: Design documents from `/specs/001-define-must-specs/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/http-api.md, quickstart.md

**Tests**: Include test tasks because this feature changes backend API contracts, auth/security behavior, inference lifecycle, and admin operations.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every task includes an explicit file path

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare config, docs, and execution scaffolding shared by all stories.

- [X] T001 Update environment variable and secret baseline in `.env.example`
- [X] T002 [P] Sync feature runbook header and prerequisites in `specs/001-define-must-specs/quickstart.md`
- [X] T003 [P] Sync contract mapping notes in `specs/001-define-must-specs/contracts/http-api.md`
- [X] T004 Add deterministic smoke runner inputs for URL/key/timeouts in `qa_smoke/run_smoke.py`
- [X] T005 Prepare feature-level pytest markers/fixtures in `backend/tests/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core contract/auth/storage/reliability foundations that block all user stories.

- [X] T006 Implement canonical model alias mapping (`wan-remix` <-> `phr00t`) in `backend/config.py`
- [X] T007 [P] Enforce source-of-truth parity validation utilities in `src/app/utils/configManager.ts`
- [X] T008 [P] Remove hardcoded model parameter constraints in `src/app/components/ControlPanel.tsx`
- [X] T009 Enforce strict auth precedence evaluation in `backend/auth.py`
- [X] T010 [P] Harden admin bootstrap/session boundary in `backend/admin_security.py`
- [X] T011 [P] Restrict CORS configuration to explicit allowlist origins in `backend/app.py`
- [X] T012 Implement auth/admin scoped rate-limiting policy in `backend/admin_security.py`
- [X] T013 Implement type-based stale task TTL transitions in `backend/storage.py`
- [X] T014 [P] Wire timeout source-of-truth constants, warm-container settings, and cache-reuse lifecycle in `backend/app.py`
- [X] T015 [P] Validate and sanitize remote workspace routing keys in `backend/app.py`
- [X] T016 Implement unified machine-readable error mapping in `backend/app.py`
- [X] T017 Add foundational auth precedence and query/header regression tests in `backend/tests/test_auth.py`
- [X] T018 [P] Add stale-task lifecycle persistence and stale-transition logging tests in `backend/tests/test_storage.py`
- [X] T019 [P] Add router/proxy boundary and CORS preflight allowlist regression tests in `backend/tests/test_api.py`

**Checkpoint**: Foundation complete, user stories can proceed independently.

---

## Phase 3: User Story 1 - Reliable Generation Lifecycle (Priority: P1) MVP

**Goal**: Users can generate image/video, poll progress, and retrieve result/preview with stable auth and lifecycle behavior.

**Independent Test**: Submit one image and one video generation, poll to terminal status, and fetch `/results` + `/preview` successfully.

### Tests for User Story 1

- [X] T020 [P] [US1] Extend generation/status/results/preview flow tests in `backend/tests/test_api.py`
- [X] T021 [P] [US1] Add schema validation tests for generation payload variants in `backend/tests/test_schemas.py`
- [X] T022 [P] [US1] Add task state transition assertions for `pending->processing->done|failed` in `backend/tests/test_storage.py`

### Implementation for User Story 1

- [X] T023 [US1] Implement generation/status/results/preview contract refinements in `backend/app.py`
- [X] T024 [P] [US1] Implement lifecycle persistence/progress updates and stale-transition log event persistence in `backend/storage.py`
- [X] T025 [P] [US1] Implement routing fallback and task dispatch safeguards in `backend/router.py`
- [X] T026 [P] [US1] Align request/response models and error payload schemas in `backend/schemas.py`
- [X] T027 [P] [US1] Align shared pipeline interfaces for progress/error propagation and warm-cache observability hooks in `backend/models/base.py`
- [X] T028 [P] [US1] Implement polling and terminal-state UX transitions in `src/app/components/MediaGenApp.tsx`
- [X] T029 [P] [US1] Implement result/preview media URL handling for auth precedence in `src/app/components/OutputPanel.tsx`
- [X] T030 [US1] Wire config-driven model/mode parameters in `src/app/components/ControlPanel.tsx`
- [X] T031 [US1] Align request auth/session behavior in `src/app/utils/sessionClient.ts`

**Checkpoint**: US1 is independently functional and demonstrable.

---

## Phase 4: User Story 2 - Persistent User Output Management (Priority: P2)

**Goal**: Users can manage completed outputs in gallery/history with consistent server state and deletion behavior.

**Independent Test**: Complete generation, confirm gallery item metadata, refresh UI, delete item, verify removal in API and UI.

### Tests for User Story 2

- [X] T032 [P] [US2] Add gallery list/delete API behavior tests in `backend/tests/test_api.py`
- [X] T033 [P] [US2] Add gallery storage projection/delete consistency tests in `backend/tests/test_storage.py`
- [X] T034 [P] [US2] Add smoke assertions for gallery lifecycle in `backend/tests/test_api.py`

### Implementation for User Story 2

- [X] T035 [US2] Implement gallery query/delete consistency and count parity in `backend/storage.py`
- [X] T036 [P] [US2] Implement gallery endpoint contract/error handling updates in `backend/app.py`
- [X] T037 [P] [US2] Implement server-synced gallery state management in `src/app/context/GalleryContext.tsx`
- [X] T038 [P] [US2] Implement gallery rendering/empty/delete UX states in `src/app/pages/GalleryPage.tsx`
- [X] T039 [P] [US2] Implement session history visualization for terminal states in `src/app/components/HistoryPanel.tsx`
- [X] T040 [US2] Wire generation completion to gallery/history updates in `src/app/components/MediaGenApp.tsx`

**Checkpoint**: US2 works independently with US1 already stable.

---

## Phase 5: User Story 3 - Safe Admin Operations for Worker Accounts (Priority: P3)

**Goal**: Admin can securely manage worker accounts, observe health transitions, and audit sensitive actions.

**Independent Test**: Admin login, accounts list, health transition to `ready`, enable/disable/deploy actions, audit verification.

### Tests for User Story 3

- [X] T041 [P] [US3] Create admin auth boundary and rate-limit tests in `backend/tests/test_admin_security.py`
- [X] T042 [P] [US3] Add encrypted account credential and status transition tests in `backend/tests/test_accounts.py`
- [X] T043 [P] [US3] Add admin endpoints and audit visibility API tests in `backend/tests/test_api.py`

### Implementation for User Story 3

- [X] T044 [US3] Implement admin bootstrap and protected-route enforcement updates in `backend/admin_security.py`
- [X] T045 [P] [US3] Implement worker account health-to-ready persistence logic in `backend/accounts.py`
- [X] T046 [P] [US3] Implement admin accounts/health/logs endpoint refinements in `backend/app.py`
- [X] T047 [P] [US3] Implement deploy subprocess secret-minimization and status commits in `backend/deployer.py`
- [X] T048 [P] [US3] Implement admin session handling updates in `src/app/admin/adminSession.ts`
- [X] T049 [P] [US3] Implement admin login/session UX updates in `src/app/admin/AdminLoginPage.tsx`
- [X] T050 [P] [US3] Implement account status and health display updates in `src/app/admin/AdminDashboard.tsx`
- [X] T051 [US3] Wire audit action feedback in admin dashboard UI in `src/app/admin/AdminDashboard.tsx`

**Checkpoint**: US3 is independently functional and auditable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final hardening, documentation, and gate execution.

- [X] T052 [P] Update operator/developer deployment notes in `README.md`
- [X] T053 [P] Update API/auth integration guidance in `API_INTEGRATION_GUIDE.md`
- [X] T054 [P] Update RU testing/operations notes in `TESTING_GUIDE_RU.md`
- [X] T055 Perform final security and secret-handling review updates in `backend/auth.py`
- [X] T056 Record backend test gate execution evidence in `specs/001-define-must-specs/quickstart.md`
- [X] T057 Record frontend build gate execution evidence in `specs/001-define-must-specs/quickstart.md`
- [X] T058 Record live smoke execution evidence in `specs/001-define-must-specs/quickstart.md`

---

## Phase 7: Security Hardening Addendum

**Purpose**: Close remaining security specification requirements (`FR-016`..`FR-024`) with implementation and verification tasks.

- [X] T059 Define secret lifecycle policy (rotation/revocation/compromise response) in `specs/001-define-must-specs/quickstart.md`
- [X] T060 [P] Enforce deterministic auth-vs-throttle precedence handling in `backend/admin_security.py`
- [X] T061 [P] Implement external token least-privilege and environment isolation checks in `backend/config.py`
- [X] T062 [P] Implement proxy target allowlist validation with structured `proxy_target_invalid` errors in `backend/app.py`
- [X] T063 Implement mandatory security event payload fields (`actor/source/action/target/outcome/timestamp/correlation_id`) in `backend/storage.py`
- [X] T064 Implement audit retention and admin-only audit access guards in `backend/storage.py`
- [X] T065 [P] Add numeric rate-limit threshold tests for auth/admin routes in `backend/tests/test_admin_security.py`
- [X] T066 [P] Add CORS preflight allowlist/denial tests (`cors_origin_blocked`) in `backend/tests/test_api.py`
- [X] T067 [P] Add secret redaction and no-plaintext-leakage regression tests in `backend/tests/test_auth.py`
- [X] T068 Add fail-closed dependency outage behavior tests for protected routes in `backend/tests/test_api.py`
- [X] T069 [P] Implement secret rotation/revocation execution path checks in `backend/auth.py`
- [X] T070 [P] Add secret rotation/revocation integration tests in `backend/tests/test_auth.py`
- [X] T071 [P] Implement tamper-evident audit chain verification in `backend/storage.py`
- [X] T072 [P] Add tamper-evidence verification tests for audit logs in `backend/tests/test_storage.py`
- [X] T073 Record incident recovery and key-rotation drill evidence in `specs/001-define-must-specs/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 -> Phase 2 -> Phase 3/4/5 -> Phase 6 -> Phase 7
- User stories depend on Phase 2 completion.
- Preferred story order: US1 (MVP) -> US2 -> US3.
- US2 and US3 can run in parallel after US1 contract-critical tasks are stable.
- Phase 7 starts after Phase 6 and acts as final security release gate.

### User Story Dependency Graph

```text
Setup + Foundational
        |
       US1 (P1)
      /   \
 US2 (P2) US3 (P3)
      \   /
      Polish
```

### Within Each User Story

- Tests before implementation updates
- Backend contract/schema before frontend wiring
- Feature wiring before polish/smoke evidence

### Parallel Opportunities

- **US1**: T024, T025, T026, T027, T028, T029 can run in parallel after T023 starts.
- **US2**: T036, T037, T038, T039 can run in parallel after T035.
- **US3**: T045, T046, T047, T048, T049, T050 can run in parallel after T044.
- **Security Addendum**: T060, T061, T062, T065, T066, T067, T069, T070, T071, T072 can run in parallel after T059.

## Implementation Strategy

### MVP First (US1)

1. Complete Phase 1 and Phase 2.
2. Deliver US1 end-to-end generation lifecycle.
3. Validate MVP via `backend/tests/test_api.py` + result retrieval checks.

### Incremental Delivery

1. Add US2 gallery/history persistence without regressing US1 flows.
2. Add US3 admin hardening and auditability.
3. Finish with Phase 6 quality gates and evidence capture.
4. Complete Phase 7 security addendum before final release gate.

### Gate Criteria Before Merge

- `pytest backend/tests/` passes.
- `npm run build` passes.
- Live smoke evidence captured in `specs/001-define-must-specs/quickstart.md`.
- Contract/config parity and security checklist findings resolved.
- Security addendum tasks (`T059`-`T073`) are completed and validated.
