# Implementation Plan: MUST Inference Platform Baseline

**Branch**: `001-define-must-specs` | **Date**: 2026-02-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-define-must-specs/spec.md`

## Summary

Stabilize and formalize the MUST baseline for Gooni Gooni inference platform: secure auth precedence,
predictable async inference lifecycle, strict contract/config parity, and auditable admin operations.
The implementation plan prioritizes eliminating contract drift, enforcing Modal reliability constraints,
and introducing explicit release gates for backend tests, smoke checks, and operational transparency.
Security completion scope includes secret lifecycle governance, deterministic auth-vs-throttle behavior,
proxy target trust validation, audit retention, and fail-closed behavior for protected routes.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript/ESM + React 18.3.1 (frontend)  
**Primary Dependencies**: FastAPI, Modal, Pydantic v2, Diffusers, Torch 2.4.0, Transformers, Vite 6  
**Storage**: Modal Volumes (`results`, `model-cache`), SQLite (`gallery.db`, sessions, accounts, audit)  
**Testing**: `pytest backend/tests/`, live API smoke (`backend/tests/test_api.py`), `npm run build`  
**Target Platform**: Modal (A10G/T4 workers + API function), GCP VM (frontend docker + nginx), browser clients  
**Project Type**: Web app (frontend + backend + admin)  
**Performance Goals**: >=95% task-id issuance <2s; stale processing cutoff image<=10m/video<=30m; no auth regression in media retrieval  
**Constraints**: GPU VRAM limits, cold starts, Volume commit/reload visibility, auth precedence (`X-API-Key` -> `api_key` -> session), CORS allowlist only, numeric auth/admin rate limits, fail-closed auth dependencies  
**Scale/Scope**: MUST baseline for 4 model families (`anisora`, `phr00t/wan-remix`, `pony`, `flux`), async queue-based generation, admin account routing

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Contract + Config Integrity**: Contract map and config source-of-truth are defined; drift points are tracked in research and contracts docs.
- [x] **Modal Reliability**: Warm-cache strategy, timeout/capacity policy, and stale-task policy are explicitly documented.
- [x] **Auth + Secrets Safety**: Auth precedence, admin boundary, CORS scope, and secret-handling constraints are explicit.
- [x] **Storage Consistency**: Commit/reload lifecycle and stale-state handling are documented as mandatory behaviors.
- [x] **Test + Transparency Gates**: Required tests, smoke gate behavior, status transitions, and audit logging gates are explicitly defined.

## Project Structure

### Documentation (this feature)

```text
specs/001-define-must-specs/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── http-api.md
└── tasks.md            # Phase 2 output (next command)
```

### Source Code (repository root)

```text
src/
├── app/
│   ├── admin/
│   ├── components/
│   ├── context/
│   ├── pages/
│   └── utils/
├── inference_settings.json
└── styles/

backend/
├── app.py
├── auth.py
├── admin_security.py
├── accounts.py
├── config.py
├── router.py
├── schemas.py
├── storage.py
├── deployer.py
├── models/
└── tests/
```

**Structure Decision**: Keep current monorepo layout and generate feature docs under `specs/001-define-must-specs/`.
No new runtime package boundary is introduced in this phase.

## Phase 0: Research Outcomes

1. Standardize Modal reliability policy:
   - keep warm container cache strategy,
   - align timeout source-of-truth to config,
   - implement type-based stale policy for processing tasks.
2. Lock security/integration boundaries:
   - strict auth precedence,
   - admin session boundary hardening,
   - CORS/rate-limit scope and proxy trust controls,
   - secret rotation/revocation, audit retention, and fail-closed routing/auth behavior.
3. Lock contract/config/test governance:
   - `src/inference_settings.json` parity gate,
   - explicit as-is vs target contract map,
   - blocking test gates (no silent pass-by-skip),
   - security release gates for secret leakage, CORS denial behavior, and mandatory audit fields.

Resolved in: [research.md](./research.md)

## Phase 1: Design & Contracts

1. Produce canonical data entities and lifecycle transitions in [data-model.md](./data-model.md).
2. Produce API/interface contract in [contracts/http-api.md](./contracts/http-api.md).
3. Produce operator/developer runbook in [quickstart.md](./quickstart.md).
4. Update AI agent context via `.specify/scripts/powershell/update-agent-context.ps1 -AgentType codex`.

## Phase 2: Planning Approach (Stop Point)

Next command (`/speckit.tasks`) will generate an executable task breakdown with:
- foundation-first sequence (contract/config/auth/storage),
- user-story phases (generation flow, gallery/history, admin operations),
- explicit test gates mapped to constitution principles,
- final security hardening addendum phase covering `FR-016`..`FR-024`.

## Post-Design Constitution Check (Re-evaluated)

- [x] **Contract + Config Integrity**: `contracts/http-api.md` + data model explicitly bind contract to config parity requirements.
- [x] **Modal Reliability**: Research and quickstart define timeout/capacity/stale operational policy.
- [x] **Auth + Secrets Safety**: Security boundaries, secret lifecycle expectations, and proxy/CORS constraints are codified in research + contracts.
- [x] **Storage Consistency**: Data model includes persistence lifecycle and stale recovery behaviors.
- [x] **Test + Transparency Gates**: Quickstart includes mandatory verification, audit/status visibility checkpoints, and security rollback gate scenarios.

## Complexity Tracking

No constitution violations requiring exception.
