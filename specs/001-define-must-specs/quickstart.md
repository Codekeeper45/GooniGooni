# Quickstart: MUST Inference Platform Baseline

## 1) Prerequisites

- Backend dependencies installed (`pip install -r backend/requirements.txt`)
- Frontend dependencies installed (`npm install`)
- Modal auth configured for deployment/testing
- Required Modal secrets available (`gooni-api-key`, `gooni-admin`, `gooni-accounts`, `huggingface` when needed)

## 2) Local Validation Steps

1. Run backend tests:
   - `pytest backend/tests/`
2. Build frontend:
   - `npm run build`
3. (Optional local route serve) Start modal local server:
   - `modal serve backend/app.py`

## 3) Live/Deployed Smoke Validation

1. Deploy backend (if required):
   - `modal deploy backend/app.py`
2. Run live API smoke:
   - `pytest backend/tests/test_api.py -v --base-url <url> --api-key <key>`

## 4) Mandatory Scenario Checklist

- Generation auth precedence works (`X-API-Key` -> `api_key` -> `gg_session`).
- Video and image generation produce task IDs and transition to terminal states.
- Stale processing policy is enforced (image<=10m, video<=30m).
- Result and preview retrieval work for browser-compatible fetch paths.
- Admin health sets ready state and persists across admin navigation.
- Audit logs include admin login and account lifecycle actions.

## 5) Operational Controls

- Verify CORS allowlist matches production frontend domain(s).
- Verify no plaintext secrets in repository or logs.
- Verify Volume commit/reload behavior for cross-container consistency.

## 6) Rollback Guidance

- If deploy introduces contract/auth regression, rollback to previous Modal app revision.
- Re-run `GET /health`, `/auth/session`, `/generate` -> `/status` -> `/results` smoke path post-rollback.
- Confirm admin routes and audit log visibility after rollback.

## 7) Gate Execution Evidence (2026-02-26)

- Backend test gate:
  - Command: `pytest backend/tests/ -q`
  - Result: `119 passed, 19 skipped in 4.01s`
- Focused backend regression gate:
  - Command: `pytest backend/tests/test_auth.py backend/tests/test_storage.py backend/tests/test_accounts.py backend/tests/test_schemas.py backend/tests/test_router.py backend/tests/test_config.py -q`
  - Result: `101 passed in 2.46s`
- Frontend build gate:
  - Command: `npm run build`
  - Result: success (`exit code 0`, `~12.3s`)
- Live smoke evidence:
  - Artifact report: `qa_smoke/artifacts/20260225_185950Z/SMOKE_REPORT.md`
  - Summary: `4 passed, 0 failed, 3 skipped` (E2E generation scenarios skipped when API key was missing)
