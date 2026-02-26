# Feature Specification: VRAM OOM Stability for Video Pipelines

**Feature Branch**: `001-fix-vram-oom`  
**Created**: 2026-02-26  
**Status**: Draft  
**Input**: User description: "Fix VRAM OOM when switching heavy video pipelines and enforce fixed video generation parameters before next deploy."

## Clarifications

### Session 2026-02-26

- Q: Should dedicated warm lanes be mandatory in production, and what should happen under GPU/quota pressure? -> A: Keep dedicated warm lanes for both heavy video models in production, with automatic fallback to single-active-pipeline mode when GPU capacity or quota is insufficient.
- Q: When a dedicated lane is unavailable, should requests queue, return 503, or run in degraded shared-worker mode? -> A: Immediately route to degraded shared-worker mode with single-active memory discipline.
- Q: What overload policy should apply in degraded mode: unlimited queue, bounded queue with timeout, or immediate 503? -> A: Use bounded queue with timeout; return `503 queue_overloaded` when limits are exceeded.
- Q: What is the maximum degraded-mode queue wait timeout? -> A: Set max wait timeout to 30 seconds.
- Q: What degraded-mode queue depth should be enforced? -> A: Set queue depth limit to 25.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stable Video Model Switching (Priority: P1)

As a user generating video with different models, I need model switching to complete without GPU out-of-memory failures.

**Why this priority**: OOM failures block the primary product flow (video generation) and make the platform unreliable.

**Independent Test**: Run alternating video generations between AniSora and Phr00t with dedicated warm execution lanes for each model; no request fails due to GPU memory exhaustion and model-switch enqueue latency stays low.

**Acceptance Scenarios**:

1. **Given** separate warm execution lanes for AniSora and Phr00t, **When** user switches model between consecutive requests, **Then** request is routed to the corresponding warm lane without unloading another heavy model first.
2. **Given** repeated alternating requests between AniSora and Phr00t, **When** requests are processed through model-dedicated lanes, **Then** tasks complete without CUDA OOM errors.
3. **Given** one lane is cold or unavailable, **When** request is submitted, **Then** request is routed to degraded shared-worker mode without memory safety violations.

---

### User Story 2 - Deterministic Video Parameter Enforcement (Priority: P2)

As an API/UI caller, I need fixed model-specific video parameters to be enforced consistently so unsupported settings are rejected early.

**Why this priority**: Invalid parameters increase runtime instability and cause avoidable inference failures.

**Independent Test**: Submit invalid parameter combinations for AniSora and Phr00t and verify deterministic 422 validation errors before inference starts.

**Acceptance Scenarios**:

1. **Given** AniSora request with steps not equal to 8, **When** request is validated, **Then** API rejects it with a validation error.
2. **Given** Phr00t request with steps not equal to 4 or cfg not equal to 1.0, **When** request is validated, **Then** API rejects it with a validation error.

---

### User Story 3 - Operational Memory Safety Visibility (Priority: P3)

As an operator, I need memory cleanup and memory usage visibility to verify stability after each video generation.

**Why this priority**: Production readiness requires observable evidence that memory pressure is controlled over time.

**Independent Test**: Inspect generation logs for post-run memory metrics and confirm cleanup executes after both success and failure paths.

**Acceptance Scenarios**:

1. **Given** a completed or failed video generation, **When** the worker exits the request flow, **Then** cleanup and memory-stat logging are executed.

---

### Edge Cases

- If no pipeline is loaded, the first request MUST follow deterministic cold-start routing and still enforce degraded queue admission limits.
- If generation fails mid-inference, cleanup and failure status MUST be persisted before the worker returns.
- If inference exceeds timeout or resource limits, the task MUST end with deterministic failure code and MUST NOT leave orphaned queue slots.
- Unsupported model aliases with fixed-parameter fields MUST fail validation before dispatch.
- If a dedicated lane is cold after deploy or autoscaling, routing MUST follow FR-020 without violating memory safety constraints.
- If degraded queue depth or wait time exceeds configured limits, the request MUST return machine-readable `503 queue_overloaded`.

## Assumptions

- In degraded mode, single-worker single-active-pipeline logic remains available as safety fallback.
- Existing auth/session behavior remains unchanged by this feature.
- Existing API error envelope remains unchanged; only validation outcomes for video parameters become stricter.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow only one active heavy video pipeline per GPU worker at any point in time.
- **FR-002**: In degraded shared-worker mode, system MUST fully release prior heavy video pipeline memory before activating a different heavy video pipeline in the same worker.
- **FR-003**: In degraded shared-worker mode, system MUST run mandatory GPU cache cleanup before loading a different heavy video pipeline.
- **FR-004**: System MUST enforce fixed AniSora video steps value of 8 at request validation time.
- **FR-005**: System MUST enforce fixed Phr00t video steps value of 4 at request validation time.
- **FR-006**: System MUST enforce fixed Phr00t cfg value of 1.0 at request validation time.
- **FR-007**: System MUST reject non-compliant fixed video parameters with deterministic validation errors before inference starts.
- **FR-008**: System MUST execute post-generation GPU memory cleanup on both success and failure paths.
- **FR-009**: System MUST emit post-generation memory usage logs for operational diagnostics.
- **FR-010**: System MUST set GPU runtime allocator configuration to reduce memory fragmentation in all GPU worker images.
- **FR-011**: System MUST provide model-dedicated video execution lanes so AniSora and Phr00t do not share the same warm heavy pipeline memory footprint.
- **FR-012**: System MUST route each video request to the execution lane dedicated to the requested model.
- **FR-013**: System MUST keep at least one warm execution instance per heavy video model in production profile when GPU capacity and quota allow.
- **FR-014**: System MUST automatically switch to a safe degraded mode that falls back to single-active-pipeline memory discipline when dedicated warm lanes are unavailable due to capacity/quota pressure.
- **FR-015**: System MUST expose operational indicators for warm-lane readiness and cold-start events.
- **FR-016**: System MUST prefer degraded shared-worker routing over immediate `503` responses when at least one safe execution path is available.
- **FR-017**: System MUST enforce bounded degraded-mode queue depth of 25 and maximum wait timeout of 30 seconds.
- **FR-018**: System MUST return machine-readable `503 queue_overloaded` when degraded queue limits are exceeded.
- **FR-019**: In model-dedicated warm lanes, system MUST keep the lane model warm between requests and MUST NOT unload it on same-model requests except worker recycle or idle-eviction events.
- **FR-020**: System MUST apply deterministic routing order: (1) dedicated warm lane if ready, (2) degraded shared-worker mode if queue admission passes, (3) machine-readable `503 queue_overloaded` otherwise.
- **FR-021**: Dedicated warm lane MUST be treated as unavailable when any of the following is true: (a) provider quota denies lane start, (b) lane health check fails for more than 60 seconds, (c) no warm lane is assigned within 30 seconds after request admission.

### API Contract & Compatibility *(mandatory)*

- Changed contract surface: `POST /generate` validation behavior for video models and additive diagnostics fields on existing admin/read responses.
- Public generation method/path remains unchanged; diagnostics updates are additive-only and non-breaking on existing admin/read surfaces.
- New strict behavior:
  - AniSora video requests with `steps != 8` return `422`.
  - Phr00t video requests with `steps != 4` or `cfg != 1.0` return `422`.
  - Degraded-mode requests exceeding queue depth 25 or 30-second wait timeout return `503 queue_overloaded`.
- Backward compatibility:
  - Backward compatible for clients already using fixed parameters.
  - Breaking for clients sending custom video steps/cfg for these models.
- Contract-to-code mapping:
  - Backend validation/update scope: `backend/schemas.py`, `backend/app.py`.
  - Frontend caller scope (if validation hints are exposed): `src/app/components/ControlPanel.tsx`, `src/app/utils/configManager.ts`.

### Configuration Source of Truth Impact *(mandatory)*

- `src/inference_settings.json` MUST reflect fixed video parameter constraints for AniSora and Phr00t.
- Companion backend model/config validation MUST stay aligned with these fixed constraints.
- No new UI hardcoded behavior is allowed outside the shared configuration source.

### Security & Secrets Impact *(mandatory)*

- API/admin auth precedence is unchanged.
- CORS policy is unchanged.
- No new secrets are introduced.
- No sensitive runtime values are logged in memory diagnostics.

### Observability & Operations *(mandatory)*

- Existing task statuses (`pending`, `processing`, `done`, `failed`) MUST remain visible to users.
- Operators MUST have logs indicating memory cleanup execution and post-generation memory allocation.
- Operators MUST have logs/metrics for warm-lane readiness and cold-start frequency per video model.
- Operators MUST have logs/metrics for fallback activation cause (`capacity`, `quota`, `manual`) and fallback duration.
- Operators MUST have logs/metrics for degraded queue depth, queue wait time, timeout drops, and `queue_overloaded` response count.
- Deployment must include rollback path if stricter validation causes client incompatibility.
- Capacity planning MUST document cost/latency tradeoff of keeping dedicated warm lanes for both heavy video models.

### Key Entities *(include if feature involves data)*

- **VideoPipelineSlot**: Represents the single active heavy video pipeline residency state in a GPU worker.
- **VideoGenerationConstraints**: Model-specific immutable validation constraints for video parameters.
- **GenerationTask**: Existing long-running inference task entity with status and failure metadata.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a controlled alternating AniSora/Phr00t run of at least 20 sequential requests with dedicated warm lanes, zero requests fail with CUDA OOM.
- **SC-002**: 100% of requests violating fixed AniSora/Phr00t parameter constraints are rejected with deterministic 422 responses before inference starts.
- **SC-003**: 100% of completed or failed video generations emit a post-generation memory cleanup log line.
- **SC-004**: In a regression run of at least 200 valid AniSora/Phr00t requests, successful task acceptance rate is at least 99% and 5xx rate does not increase by more than 1 percentage point versus baseline.
- **SC-005**: In warm-lane conditions, at least 95% of model-switch requests receive task acceptance response within 3 seconds.
- **SC-006**: After deploy or autoscale events, warm-lane readiness for each heavy video model is reached within 10 minutes in at least 95% of events.
- **SC-007**: Under sustained degraded-mode load test, queue limit enforcement is deterministic and overloaded requests return `503 queue_overloaded` with no memory-safety regressions.
- **SC-008**: Under degraded-mode load, no request waits in queue longer than 30 seconds before acceptance or deterministic `503 queue_overloaded`.
- **SC-009**: Under degraded-mode load, queue depth never exceeds 25 and overflow handling remains deterministic.
