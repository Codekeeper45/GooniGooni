# Gooni Gooni Inference Audit Report

Date: February 25, 2026  
Environment: production Modal backend (`https://yapparov-emir-f--gooni-api.modal.run`) + frontend on GCP VM (`http://34.73.173.191`)

## Scope
- Backend API audit (auth, health, models, gallery, generate/status/results flow)
- Production inference E2E (2 image + 2 video scenarios)
- Browser-agent UI E2E via `browser-use-control` workflow
- Test suite stabilization for backend regression checks

## What Passed
- `GET /health` responds `200` with expected payload.
- Auth protections are active:
  - `GET /models` without API key => `403`
  - `GET /admin/health` without admin key => `403`
- Backend read-only API smoke checks passed:
  - `pytest backend/tests/test_api.py -k "not GenerateFlow"` => `9 passed`.
- Repository tests stabilized:
  - `pytest backend/tests -q` => `120 passed, 11 skipped`.

## Critical Findings

### P0: Inference jobs are accepted but never progress
- `POST /generate` returns `202` and task IDs, but `/status/{id}` remains `pending` with `progress: 0` for extended periods.
- Reproduced for all tested models:
  - `pony`: `767d7238-e518-4990-98d6-e68c1e120217`
  - `flux`: `56ac7a0f-6611-4957-9b43-3edc53c9b425`
  - `phr00t`: `a3269cfd-231d-4b0a-8ba4-530c43729576`
  - `anisora`: `9174afd3-0932-4654-bed6-bb83340971d8`
- Bulk E2E run timed out (images: ~426s, videos: ~900s+) with no terminal state.
- Volume DB snapshot confirms a queue of pending tasks (11 rows, all `pending`).

### P1: Browser-agent E2E blocked by unavailable LLM proxy
- `browser-use-control` preflight passed for script/imports.
- Agent execution failed after initial navigation due repeated `ModelProviderError: Connection error`.
- Root cause: configured `OPENAI_BASE_URL=http://127.0.0.1:8045/v1` was unreachable (connection refused).

## Fixes Implemented in Repository
- Added shared live-test options/fixtures in `backend/tests/conftest.py`.
- Fixed outdated Pony model expectation in `backend/tests/test_config.py`.
- Enforced non-empty `prompt` validation in `backend/schemas.py`.
- Aligned `backend/requirements.txt` with deployed Torch version (`2.4.0`).
- Removed per-file pytest option hook from `backend/tests/test_api.py` (now centralized in `conftest.py`).

## Recommended Next Actions
1. Inspect Modal function dispatch for `run_image_generation` / `run_video_generation` and confirm worker containers start for queued tasks.
2. Add server-side watchdog for stale `pending` tasks (auto-mark `failed` with reason after timeout).
3. Ensure status updates are externally visible during long runs (commit/status sync strategy).
4. Restore browser-agent LLM endpoint at `127.0.0.1:8045` or switch to a reachable OpenAI-compatible provider.
