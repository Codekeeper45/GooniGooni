<!--
Sync Impact Report
Version change: 1.0.0 -> 1.1.0
Modified principles:
- I. API Contract Integrity -> I. Contract and Configuration Integrity
- II. Modal Inference Reliability (materially expanded)
- III. Security and Secret Hygiene -> III. Authentication and Secret Safety
- IV. Test-Gated Delivery (materially expanded)
- V. Observability and User Transparency -> V. State Transparency and Auditability
Added sections:
- None
Removed sections:
- None
Templates requiring updates:
- ✅ .specify/templates/plan-template.md
- ✅ .specify/templates/spec-template.md
- ✅ .specify/templates/tasks-template.md
- ⚠ pending: .specify/templates/commands/*.md (directory absent)
Runtime guidance review:
- ✅ project.md reviewed and aligned
- ✅ README.md, AGENTS.md, CLAUDE.md, GEMINI.md, QWEN.md reviewed; no mandatory edits required
Follow-up TODOs:
- None
-->
# Gooni Gooni Constitution

## Core Principles

### I. Contract and Configuration Integrity
Frontend-backend contract changes MUST be explicit and synchronized. Any request/response change
MUST be reflected in `backend/schemas.py`, backend routes, `src/inference_settings.json`, and
`src/app/utils/configManager.ts`. `src/inference_settings.json` MUST remain the single source of
truth for model parameters, field visibility, and ranges; UI components MUST NOT hardcode these
rules. Adding or changing a model MUST update `backend/models/`, `backend/config.py`,
`backend/app.py` dispatch, and related tests in one change set.
Rationale: contract or config drift breaks generation flows and creates silent UI/backend mismatch.

### II. Modal Inference Reliability
Inference code MUST optimize for warm-container reuse and predictable resource usage. Heavy model
weights MUST load once per warm container (`@modal.enter` or equivalent cache). Every generation
task MUST progress through `pending -> processing -> done|failed`, with persisted progress and
result/error metadata. GPU profile, timeout, and concurrency limits MUST be explicit in Modal
declarations. Pipelines created via `from_pipe(...)` MUST NOT re-apply
`enable_model_cpu_offload()` to shared components.
Rationale: this project is bottlenecked by GPU memory, cold starts, and long-running jobs.

### III. Authentication and Secret Safety
Secrets MUST never be committed to the repository. Runtime credentials MUST be provided through
Modal secrets or local `.env` files derived from `.env.example`. API authentication MUST support
`X-API-Key` and `api_key` query parameter for browser media fetching paths; admin session bootstrap
MUST require `X-Admin-Key` header only. Key comparison MUST use `hmac.compare_digest`, and full
key values MUST NOT be logged. Stored worker token secrets MUST be encrypted with Fernet using
`ACCOUNTS_ENCRYPT_KEY` from `gooni-accounts`. Production CORS MUST be restricted to approved
frontend origins.
Rationale: the service handles privileged keys and expensive compute resources.

### IV. Test-Gated Delivery
Backend modifications MUST pass `pytest backend/tests/` before merge. Changes affecting API,
auth/session behavior, routing, storage lifecycle, or model dispatch MUST include targeted test
updates in corresponding backend test modules. Changes affecting real inference flow MUST include
at least one live smoke validation (`backend/tests/test_api.py` against deployed URL) with command
and outcome captured in PR notes.
Rationale: regressions are expensive and usually appear only in end-to-end flows.

### V. State Transparency and Auditability
Long-running operations MUST expose user-visible state transitions and actionable error details.
Status payloads MUST make task progress understandable to users. Generation and admin actions
SHOULD log task ID, model key, and routing context when available. Admin-affecting operations MUST
be auditable through persistent audit records.
Rationale: users and operators need clear status when inference takes minutes and spans workers.

## Operational Constraints

- Frontend stack is React + TypeScript + Vite in `src/`; backend stack is Python + FastAPI + Modal
  in `backend/`.
- SQLite metadata and generated artifacts are stored in Modal Volume `results`; write paths MUST
  commit and read paths MUST reload when cross-container visibility is required.
- Backend deploy path is `modal deploy backend/app.py`; frontend deploy path is Docker image rollout
  on the GCP VM.
- Repository conventions in `AGENTS.md` remain authoritative for naming, formatting, and PR
  metadata.

## Development Workflow and Quality Gates

1. Define scope in spec and capture contract, config, auth, and operational implications.
2. Pass Constitution Check in plan before implementation and after design refinement.
3. Implement minimal changes while preserving lifecycle states, storage consistency, and auditability.
4. Verify with required gates (`pytest backend/tests/`, `npm run build`, plus smoke when required).
5. For deploy-impacting changes, include smoke evidence and rollback notes in PR.

## Governance

This constitution supersedes ad-hoc practices for this repository. Amendments require:
1. a documented change in `.specify/memory/constitution.md`,
2. updates to dependent templates under `.specify/templates/`,
3. version bump by semantic policy:
   - MAJOR: incompatible governance changes or principle removal/redefinition,
   - MINOR: new principle/section or materially expanded policy,
   - PATCH: clarification-only wording updates.
Compliance is reviewed in every PR through plan/spec/tasks artifacts and verification evidence.

**Version**: 1.1.0 | **Ratified**: 2026-02-26 | **Last Amended**: 2026-02-26
