# Feature Specification: MUST Inference Platform Baseline

**Feature Branch**: `001-define-must-specs`  
**Created**: 2026-02-26  
**Status**: Draft  
**Input**: User description: "C:\Users\yappa\OneDrive\MyFolder\myProjects\Веб приложение Gooni Gooni\gooni-must-specs-v2.md вот мои требования к спецификации, изучи их"

## Clarifications

### Session 2026-02-26

- Q: What authentication precedence should the system enforce across generation and media flows? → A: `X-API-Key` header, then `api_key` query, then `gg_session` cookie fallback.
- Q: What stale-task timeout policy should mark stuck processing as failed? → A: Type-based TTL: image >10 minutes, video >30 minutes.
- Q: How should worker account status transition after health checks? → A: Successful health-check immediately sets account status to `ready` and persists until explicit admin action or explicit failure.
- Q: What should be the primary authentication model for UI users? → A: Session cookie is primary for UI flows; API key remains server-side secret and fallback compatibility channel.
- Q: What API rate-limiting scope should be enforced? → A: Rate limiting applies to auth/admin-critical endpoints; inference endpoints are governed by queue/worker capacity controls.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reliable Generation Lifecycle (Priority: P1)

A creator submits a prompt, starts generation, tracks progress, and receives a playable/downloadable result without manual backend intervention.

**Why this priority**: This is the core product value; without a stable generation lifecycle the application is unusable.

**Independent Test**: Submit one video task and one image task, poll until terminal status, then fetch result and preview for each task.

**Acceptance Scenarios**:

1. **Given** a valid authenticated user and valid parameters, **When** the user sends a generation request, **Then** the system returns a task identifier immediately and starts asynchronous processing.
2. **Given** a running task, **When** the user polls status, **Then** the system returns current status and progress until `done` or `failed`.
3. **Given** a completed task, **When** the user requests result and preview, **Then** media is returned with the correct content type.

---

### User Story 2 - Persistent User Output Management (Priority: P2)

A creator can view generated outputs in gallery/history, keep context across navigation, and remove obsolete outputs.

**Why this priority**: Users need confidence that completed work is visible and manageable after long-running inference.

**Independent Test**: Complete a task, verify it appears in gallery with metadata, refresh/reopen UI, then delete the item and confirm removal from API and UI.

**Acceptance Scenarios**:

1. **Given** completed tasks, **When** the user opens gallery, **Then** only completed items are listed in reverse chronological order with preview links.
2. **Given** a gallery item, **When** the user deletes it, **Then** metadata and stored files are removed and the item disappears from the UI.

---

### User Story 3 - Safe Admin Operations for Worker Accounts (Priority: P3)

An administrator authenticates, reviews worker health, manages account states, and audits security-critical actions.

**Why this priority**: Stable operations and incident response depend on secure account control and auditability.

**Independent Test**: Authenticate as admin, list accounts, run health check, change account state, deploy one account, and confirm audit entries are created.

**Acceptance Scenarios**:

1. **Given** a valid admin session, **When** the admin accesses account management endpoints, **Then** account data and health status are returned with no unauthorized access.
2. **Given** an admin action (enable/disable/deploy), **When** the action succeeds or fails, **Then** a corresponding audit log entry is recorded.

---

### Edge Cases

- What happens when authentication is missing or invalid (`X-API-Key`, `api_key`, session cookie)? Requests are rejected with structured error payloads.
- How does system handle unavailable workers? Generation request returns actionable "no workers" failure without creating orphaned running state.
- What is the fallback when long-running inference exceeds timeout/resource limits? Task is finalized as `failed` with actionable user error and operator logs.
- What happens when result metadata exists but file is missing? Result endpoint returns "gone" response and preserves traceability in status/history.
- How does system handle stale distributed state? Read paths force state refresh and write paths persist state so API and workers stay consistent.
- How does system handle stale `processing` tasks? Tasks exceeding TTL are auto-marked `failed` (`image` >10 minutes, `video` >30 minutes).
- How are auth error classes differentiated? Missing/invalid API credentials return `invalid_api_key`, missing session returns `session_required`, expired/revoked session returns `session_expired`, and throttled auth/admin requests return `rate_limited`.
- How are CORS preflight failures handled? Origins outside allowlist return structured `cors_origin_blocked` and no credentialed CORS headers.
- How are proxy trust failures handled? Unknown/invalid workspace targets return structured `task_not_found` or `proxy_target_invalid` and MUST NOT forward secrets.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support generation authentication with precedence `X-API-Key` header → `api_key` query → `gg_session` cookie fallback, with explicit failure responses.
- **FR-002**: System MUST create a durable task record before asynchronous inference dispatch.
- **FR-003**: System MUST support video and image generation flows with model/mode validation from a shared model configuration source.
- **FR-004**: System MUST expose task polling with statuses `pending`, `processing`, `done`, and `failed`, including numeric progress.
- **FR-005**: System MUST expose result and preview retrieval endpoints that work for browser media elements and API clients.
- **FR-006**: System MUST persist lifecycle transitions so task state survives container restarts and page reloads.
- **FR-007**: System MUST provide gallery listing and deletion for completed outputs, including metadata and storage cleanup.
- **FR-008**: System MUST provide admin-only account lifecycle operations (create, read, update status, deploy trigger, delete) and preserve account status across admin page reloads.
- **FR-009**: System MUST provide public and admin health endpoints covering runtime availability and operational readiness.
- **FR-010**: System MUST emit standardized machine-readable error payloads for validation, auth, routing, processing, and storage failures.
- **FR-011**: System MUST support remote workspace task routing and proxying for generation, status, result, and preview flows.
- **FR-012**: System MUST record security and admin actions in an audit log with timestamp, actor context, action, and outcome.
- **FR-013**: System MUST automatically mark stale `processing` tasks as `failed` when runtime exceeds TTL (`image` >10 minutes, `video` >30 minutes).
- **FR-014**: System MUST transition worker accounts to `ready` immediately after successful health check and MUST NOT reset them to `pending` on admin UI navigation.
- **FR-015**: System MUST enforce rate limiting on authentication and admin-critical endpoints, while inference endpoints are constrained through worker capacity and queue controls.
- **FR-016**: System MUST enforce secret lifecycle controls for API/admin/session credentials: issuance source, rotation interval, compromise-triggered revocation, and recovery procedure MUST be documented and testable.
- **FR-017**: System MUST protect worker account credentials at rest and in transit (encrypted-at-rest, TLS in transport) and MUST NOT expose raw credential values in logs, errors, or audit payloads.
- **FR-018**: System MUST enforce numeric rate-limit thresholds: `POST /auth/session` <=10 requests/min/IP, `POST /admin/session` <=30 requests/60s/IP, and other `/admin/*` endpoints <=120 requests/min/session.
- **FR-019**: System MUST define deterministic precedence between authorization and throttling checks for auth/admin routes and return exactly one structured error class per rejected request.
- **FR-020**: System MUST validate remote workspace identifiers against strict format (`^[a-z0-9-]{3,64}$`) and resolve proxy targets only from known account registry entries before forwarding requests.
- **FR-021**: System MUST emit structured security observability events with mandatory fields (`actor`, `source`, `action`, `target`, `outcome`, `timestamp`, `correlation_id`).
- **FR-022**: System MUST enforce audit-log governance: minimum retention 90 days, admin-only access, append-only write model, and tamper-evident storage expectations.
- **FR-023**: System MUST define fail-closed behavior for auth/security dependencies: when secret store or auth/session storage is unavailable, protected routes return structured denial responses and do not allow degraded anonymous access.
- **FR-024**: System MUST require least-privilege scopes for external provider tokens (model download/inference only) and explicitly document forbidden privilege scopes.

### API Contract & Compatibility *(mandatory)*

| Contract | Required Behavior | Backend Files | Frontend Call Sites | Compatibility |
|---|---|---|---|---|
| `POST /auth/session`, `GET /auth/session`, `DELETE /auth/session` | Session issue/check/revoke for generation access | `backend/app.py`, `backend/auth.py`, `backend/storage.py` | `src/app/utils/sessionClient.ts` | Backward compatible (new/expanded) |
| `POST /generate` | Validate payload, create task, async dispatch, immediate task ID | `backend/app.py`, `backend/schemas.py`, `backend/router.py`, `backend/storage.py` | `src/app/components/ControlPanel.tsx`, `src/app/components/MediaGenApp.tsx` | Backward compatible |
| `GET /status/{task_id}` | Progress polling with terminal state semantics | `backend/app.py`, `backend/storage.py` | `src/app/components/MediaGenApp.tsx` | Backward compatible |
| `GET /results/{task_id}` and `GET /preview/{task_id}` | Return media for browser and API clients, support remote tasks | `backend/app.py`, `backend/storage.py`, `backend/auth.py` | `src/app/components/OutputPanel.tsx`, `src/app/pages/GalleryPage.tsx` | Backward compatible |
| `GET /gallery`, `DELETE /gallery/{task_id}` | List completed outputs and delete output + metadata | `backend/app.py`, `backend/storage.py` | `src/app/context/GalleryContext.tsx`, `src/app/pages/GalleryPage.tsx` | Backward compatible |
| `GET /health`, `GET /admin/health`, `GET /admin/logs`, `/admin/accounts*` | Runtime/admin monitoring and account operations | `backend/app.py`, `backend/accounts.py`, `backend/admin_security.py`, `backend/deployer.py` | `src/app/admin/*` | Backward compatible |

### Configuration Source of Truth Impact *(mandatory)*

- `src/inference_settings.json` MUST remain the single source of truth for model catalog, mode availability, and UI-exposed parameter constraints.
- Required model families for this baseline are `anisora`, `phr00t` (alias: `wan-remix`) for video, and `pony`, `flux` for image, with explicit `type`, `mode`, and parameter boundary definitions.
- Any model/mode/parameter change MUST be mirrored in `backend/config.py` validation and request handling in `backend/app.py`.
- UI MUST NOT introduce hardcoded model visibility or parameter constraints that diverge from `src/inference_settings.json`.

### Security & Secrets Impact *(mandatory)*

- Generation access MUST enforce auth precedence `X-API-Key` header → `api_key` query → `gg_session` cookie fallback.
- UI authentication flows MUST use `gg_session` cookie as the primary mechanism; API key handling remains infrastructure-level and MUST NOT be required as manual user input.
- Admin authentication MUST enforce strict boundary: `POST /admin/session` accepts `X-Admin-Key` header only; all other `/admin/*` routes require a valid admin session and MUST NOT accept admin credentials via query parameters.
- Rate limiting MUST protect auth/admin surfaces with numeric thresholds (`/auth/session`: 10/min/IP, `/admin/session`: 30/60s/IP, `/admin/*`: 120/min/session); inference endpoints (`generate`, `status`, `results`, `preview`) use capacity-based controls.
- Auth/throttle precedence MUST be deterministic: for auth/admin endpoints, throttle is evaluated first; if throttled return `rate_limited`; otherwise evaluate auth and return the specific auth error code.
- CORS policy MUST explicitly allow only approved frontend origins from an environment-defined allowlist (for example, `FRONTEND_ORIGINS`); wildcard production policy is out of scope for acceptance.
- CORS requirements MUST include credentialed preflight behavior: allowed origins receive explicit CORS headers; denied origins return `cors_origin_blocked` without credentialed CORS headers.
- Secrets (API key, admin key, model provider tokens, account encryption key) MUST be sourced from secure secret management and MUST NOT be stored in plaintext in repository files.
- Secret lifecycle MUST define rotation cadence (<=90 days), immediate rotation on compromise, and explicit revocation of affected sessions/keys.
- Worker account tokens MUST remain encrypted at rest (Fernet or equivalent) and MUST NOT be sent to unvalidated proxy targets.
- External provider tokens MUST use least-privilege permissions and be isolated per environment (dev/stage/prod).

### Observability & Operations *(mandatory)*

- User-visible status events MUST include `pending`, `processing`, `done`, and `failed`, with progress updates sufficient for long-running inference feedback.
- Operator logs MUST include task dispatch decisions, worker routing outcome, terminal task state, and admin account actions.
- Audit events MUST capture admin login attempts, account CRUD/status/deploy actions, and security throttling decisions, with mandatory fields: `actor`, `source`, `action`, `target`, `outcome`, `timestamp`, `correlation_id`.
- Stale-transition events MUST be logged with task type, runtime duration, and applied TTL threshold.
- Security events MUST include secret-access denials, proxy-target validation failures, and CORS origin denials.
- Audit logs MUST be retained for at least 90 days and remain admin-only readable.
- Deployment changes MUST support rollback by preserving prior working configuration and avoiding schema-breaking API contract changes in this baseline.
- Security release gate MUST include rollback validation for auth/routing changes: post-rollback checks for `/auth/session`, `/generate` -> `/status`, `/results`, and `/admin/health` are required.

### Key Entities *(include if feature involves data)*

- **Task**: Represents one generation request with identity, model/mode/type, prompt/parameters, lifecycle status, progress, and output locations.
- **Generation Session**: Represents time-bound user access context with issue time, expiry, and revocation state.
- **Worker Account**: Represents a dispatchable backend workspace with credentials, status (`pending`, `ready`, `failed`, `disabled`), and health metadata; successful health check transitions to `ready` and that state persists until explicit admin action or explicit failure.
- **Gallery Item**: Represents user-visible completed output metadata and preview/result references.
- **Admin Audit Event**: Represents immutable record of admin/security actions with timestamp, actor context, action type, and success flag.
- **Model Configuration Entry**: Represents validated model/mode/parameter rules synchronized between UI and backend validation.

### Assumptions

- This feature defines the MUST baseline only; payments, user profiles, public sharing, and frontend automated test suites are out of scope.
- Existing frontend routes and page structure remain; this scope focuses on behavioral correctness and contract consistency.
- Live inference may take minutes; asynchronous polling remains the default interaction model.
- Auth and secret dependencies are treated as fail-closed services for protected routes.
- Modal secrets, workspace routing registry, and provider-token scope policies are trusted only when explicit validation checks succeed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 95% of valid generation requests return a task identifier within 2 seconds under a sustained load of 10 concurrent submission requests.
- **SC-002**: At least 95% of submitted tasks reach a terminal state (`done` or `failed`) with no orphaned `processing` state beyond 10 minutes for image tasks or 30 minutes for video tasks.
- **SC-003**: 100% of baseline UI smoke scenarios complete without manual API-key entry by end users, and media retrieval (browser playback/download) completes without authentication-regression errors.
- **SC-004**: 100% of successful worker health checks transition account status to `ready`, remain persisted across admin page reloads, and are reflected in health/audit views within one polling interval (<=5 seconds).
- **SC-005**: 100% of API error responses for covered endpoints follow the agreed structured error schema.
- **SC-006**: 100% of auth/admin rejection cases in contract tests return the expected unique code (`invalid_api_key`, `session_required`, `session_expired`, `rate_limited`, `cors_origin_blocked`) with no ambiguous overlap.
- **SC-007**: 100% of security/audit events generated in smoke tests include mandatory fields (`actor`, `source`, `action`, `outcome`, `timestamp`, `correlation_id`).
- **SC-008**: 0 plaintext secret values appear in application logs, error payloads, or audit records during backend test and smoke execution.

