# Research: MUST Inference Platform Baseline

## Decision 1: Modal Reliability Policy (warm cache + capacity + stale control)

**Decision**
- Keep per-container lazy pipeline caching for video/image workers.
- Preserve explicit `min_containers` defaults to keep warm workers for critical paths.
- Normalize timeout values via one source-of-truth policy (config-driven).
- Enforce stale-task auto-fail policy by task type for `processing` tasks:
  - image > 10 minutes
  - video > 30 minutes

**Rationale**
- Existing implementation already caches pipelines per warm container; policy must make this deterministic.
- GPU constraints and cold starts require stable capacity rules instead of ad-hoc tuning.
- Spec FR-013 and SC-002 demand typed stale limits and terminal-state guarantees.

**Alternatives considered**
- Keep current broad stale sweep (hourly / single threshold): rejected due to spec mismatch and long-lived stuck states.
- Disable warm workers to reduce cost: rejected due to latency instability for first requests.

## Decision 2: Security Boundary and Auth Precedence

**Decision**
- Canonical auth precedence for generation/media flows remains:
  1. `X-API-Key`
  2. `api_key` query
  3. `gg_session` cookie fallback
- UI user flow is session-first; manual user API-key input is not required.
- Admin boundary is session-based after bootstrap; `x-admin-key` is bootstrap credential only.
- Rate limiting scope targets auth/admin surfaces; inference endpoints are controlled by queue/capacity.

**Rationale**
- Preserves browser media compatibility while avoiding precedence ambiguity.
- Reduces exposure of long-lived admin credentials.
- Avoids blocking valid long-running inference requests with overly broad request throttles.

**Alternatives considered**
- Session-first globally: rejected due to API/client incompatibility.
- API-key-only everywhere: rejected due to UX/security tradeoff for browser usage.
- Global endpoint rate limit: rejected due to false throttling on long-running workflows.

## Decision 3: Contract/Config Parity as Governance Gate

**Decision**
- `src/inference_settings.json` is treated as canonical parameter/config source for model controls.
- Enforce parity mapping among:
  - `src/inference_settings.json`
  - frontend config usage (`src/app/utils/configManager.ts`, component forms)
  - backend validation/dispatch (`backend/config.py`, `backend/app.py`, schemas)
- Track as-is vs target contract map explicitly in `contracts/http-api.md`.

**Rationale**
- Prior reviews and current code show drift risk between UI defaults, schema constraints, and backend routing.
- Constitution requires contract/config integrity and synchronized updates.

**Alternatives considered**
- Manual synchronization without explicit mapping: rejected due to repeated regressions.
- Move source-of-truth to backend-only endpoint immediately: deferred (larger refactor not required for this planning phase).

## Decision 4: Test and Transparency Gates Are Blocking

**Decision**
- Required verification gates for this feature remain blocking:
  - `pytest backend/tests/`
  - live API smoke (when target URL/key provided)
  - `npm run build`
- Gate reporting must include status transition visibility and audit visibility checks.

**Rationale**
- Feature scope directly impacts auth, routing, lifecycle persistence, and admin operations.
- Silent skipped checks create false confidence and delay regressions to production.

**Alternatives considered**
- Make smoke checks purely optional: rejected for release gating.
- Block only unit tests/build: accepted only as local dev fallback, not release gate.

## Decision 5: Remote Workspace Proxy Hardening

**Decision**
- Keep remote routing support but treat `workspace::id` parsing as sensitive boundary.
- Require strict workspace identifier validation and controlled target resolution policy.
- Include proxy-failure/error-contract requirements in interface contract.

**Rationale**
- Remote task proxying is necessary for account-router architecture.
- Unbounded task-id derived routing can create trust confusion and secret leakage risk.

**Alternatives considered**
- Remove remote proxying from scope: rejected (breaks multi-account architecture).
- Keep direct unsanitized interpolation: rejected due to security risk.

## Resolved Clarifications

All technical-context unknowns and integration dependencies were resolved in this document; no remaining
`NEEDS CLARIFICATION` markers remain for planning.
