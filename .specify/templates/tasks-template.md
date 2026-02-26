---

description: "Task list template for feature implementation"
---

# Tasks: [FEATURE NAME]

**Input**: Design documents from `/specs/[###-feature-name]/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Include test tasks whenever backend, API contract, inference flow, or auth/security behavior is changed.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app (this repo)**: `src/` for frontend and `backend/` for API/inference.
- Frontend features: `src/app/components/`, `src/app/pages/`, `src/app/admin/`, `src/app/utils/`.
- Backend features: `backend/app.py`, `backend/schemas.py`, `backend/storage.py`, `backend/models/`, `backend/tests/`.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create/update feature branch scaffolding and docs under `specs/[###-feature-name]/`
- [ ] T002 Identify impacted frontend and backend files for contract mapping
- [ ] T003 [P] Document required secrets/env changes in `.env.example` or deployment notes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

- [ ] T004 Implement/update schemas and shared contracts in `backend/schemas.py`
- [ ] T005 [P] Implement/update source-of-truth config wiring in `src/inference_settings.json` and `src/app/utils/configManager.ts`
- [ ] T006 [P] Implement/update auth/CORS/secret guards in backend middleware/dependencies
- [ ] T007 [P] Ensure task lifecycle + status transitions + storage commit/reload behavior in `backend/storage.py` and `backend/app.py`
- [ ] T008 Implement/update logging/audit hooks for affected flows
- [ ] T009 Define test plan: unit/integration/live smoke scope for this feature

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - [Title] (Priority: P1) MVP

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 1

- [ ] T010 [P] [US1] Add/update backend unit tests in `backend/tests/test_[module].py`
- [ ] T011 [P] [US1] Add/update API integration test in `backend/tests/test_api.py` (if endpoint flow changed)

### Implementation for User Story 1

- [ ] T012 [P] [US1] Implement backend changes in `backend/[file].py`
- [ ] T013 [P] [US1] Implement frontend changes in `src/app/[path].tsx`
- [ ] T014 [US1] Wire frontend/backend contract, config mapping, and error handling
- [ ] T015 [US1] Add/adjust user-visible status/progress UI where applicable

**Checkpoint**: User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - [Title] (Priority: P2)

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 2

- [ ] T016 [P] [US2] Add/update backend tests in `backend/tests/`
- [ ] T017 [P] [US2] Add/update frontend verification (build/runtime assertions)

### Implementation for User Story 2

- [ ] T018 [P] [US2] Implement backend changes in `backend/[file].py`
- [ ] T019 [P] [US2] Implement frontend changes in `src/app/[path].tsx`
- [ ] T020 [US2] Validate compatibility with existing user stories

**Checkpoint**: User Stories 1 and 2 should both work independently

---

## Phase 5: User Story 3 - [Title] (Priority: P3)

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 3

- [ ] T021 [P] [US3] Add/update backend tests in `backend/tests/`
- [ ] T022 [P] [US3] Add/update live smoke validation evidence if inference path changed

### Implementation for User Story 3

- [ ] T023 [P] [US3] Implement backend changes in `backend/[file].py`
- [ ] T024 [P] [US3] Implement frontend changes in `src/app/[path].tsx`
- [ ] T025 [US3] Validate observability/audit updates and rollback behavior

**Checkpoint**: All user stories should now be independently functional

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T026 [P] Documentation updates in `README.md` and relevant guides
- [ ] T027 Code cleanup and refactoring
- [ ] T028 Performance/resource optimization across affected inference paths
- [ ] T029 [P] Security hardening and secret-handling review
- [ ] T030 Run required verification commands (`pytest backend/tests/`, `npm run build`)
- [ ] T031 Run live smoke (`pytest backend/tests/test_api.py -v --base-url <url> --api-key <key>`) when applicable

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: Depend on Foundational phase completion
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### Within Each User Story

- Tests are written/updated before implementation when behavior changes
- Schemas/contracts before endpoint and UI wiring
- Core implementation before integration and smoke validation
- Story complete before moving to next priority

### Parallel Opportunities

- Tasks marked [P] can run in parallel when they touch independent files
- Backend and frontend implementation tasks can run in parallel after contracts are fixed
- Different user stories can be worked on in parallel if dependencies are satisfied

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to user story for traceability
- Each user story should be independently completable and testable
- Include exact command evidence in PR notes for required gates
