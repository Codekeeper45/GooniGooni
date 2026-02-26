# Quickstart: VRAM OOM Stability for Video Pipelines

## 1) Prerequisites

- Backend deps installed (`pip install -r backend/requirements.txt`)
- Frontend deps installed (`npm install`)
- Modal auth configured
- Required secrets configured (`gooni-api-key`, `gooni-admin`, `gooni-accounts`, optional `huggingface`)

## 2) Local Validation

1. Run backend tests:
   - `pytest backend/tests/`
2. Run focused stability tests (after implementation):
   - `pytest backend/tests/test_api.py -k "queue_overloaded or video"`
   - `pytest backend/tests/test_schemas.py -k "anisora or phr00t"`
3. Build frontend:
   - `npm run build`

## 3) Deploy Validation

1. Deploy backend:
   - `modal deploy backend/app.py`
2. Verify health:
   - `GET /health`
3. Optional live smoke:
   - `pytest backend/tests/test_api.py -v --base-url <url> --api-key <key>`

## 4) Mandatory Feature Scenarios

- Dedicated lane routing:
  - Consecutive AniSora requests stay on AniSora lane without OOM.
  - Consecutive Phr00t requests stay on Phr00t lane without OOM.
- Model switching:
  - Alternating AniSora <-> Phr00t requests do not fail with CUDA OOM.
- Fixed parameter enforcement:
  - AniSora with `steps!=8` returns `422`.
  - Phr00t with `steps!=4` or `cfg!=1.0` returns `422`.
- Degraded queue behavior:
  - Under simulated pressure, request admission follows depth `25` and wait timeout `30s`.
  - Breach returns deterministic `503 queue_overloaded`.

## 5) Operational Checks

- Confirm allocator env is present in GPU workers:
  - `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
- Confirm memory cleanup and post-generation memory logs are emitted.
- Confirm fallback metrics/logs include cause (`capacity|quota|manual`) and duration.
- Confirm queue metrics/logs include depth, wait, timeout drops, and overload count.

## 6) Rollback

- If strict validation or queue policy causes regression:
  1. Roll back backend deploy to previous stable revision.
  2. Re-run `/health` and basic generate->status flow.
  3. Verify no auth/session/CORS regressions.

## 7) Implementation Checklist

- [x] Dedicated warm lanes for `anisora` and `phr00t` are enabled.
- [x] Degraded queue policy is enforced (`depth=25`, `wait<=30s`).
- [x] Machine-readable `503 queue_overloaded` is returned on overload.
- [x] Fixed video parameters are validated (`anisora steps=8`, `phr00t steps=4,cfg=1.0`).
- [x] CUDA allocator anti-fragmentation env is enabled.
- [x] Operational diagnostics are emitted and visible in admin APIs.

## 8) Verification Log

- 2026-02-26 local backend regression:
  - Command: `pytest backend/tests -q`
  - Result: `137 passed, 24 skipped in 2.92s`
- 2026-02-26 frontend build gate:
  - Command: `npm run build`
  - Result: `vite build succeeded` (bundle emitted to `dist/`)
- Live smoke (manual, after deploy):
  - Pending evidence capture with real environment URL and API key.
  - Switching: alternate `anisora` <-> `phr00t` requests and verify no CUDA OOM.
  - Overload: saturate degraded queue and verify deterministic `503 queue_overloaded`.
