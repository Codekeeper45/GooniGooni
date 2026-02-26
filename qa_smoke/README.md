# QA Smoke Runner

This folder contains a Playwright-based smoke suite for the deployed app.

## What It Covers

- UI availability and core controls.
- Model/type/mode switching (`AniSora`, `Phr00t WAN 2.2`, image models).
- Negative checks:
  - generate without prompt,
  - unsupported reference file type.
- Full image chain (requires API key):
  - generate -> view -> download -> gallery -> delete.
- Video smoke start checks for:
  - `AniSora` T2V,
  - `Phr00t WAN 2.2` T2V.

## Run

Playwright is already available in `Browser-USE/.venv`, so use that Python:

```powershell
& "C:\Users\yappa\OneDrive\MyFolder\myProjects\Browser-USE\.venv\Scripts\python.exe" `
  qa_smoke\run_smoke.py --headless
```

With API key (required for generation scenarios):

```powershell
$env:E2E_API_KEY="your_x_api_key"
& "C:\Users\yappa\OneDrive\MyFolder\myProjects\Browser-USE\.venv\Scripts\python.exe" `
  qa_smoke\run_smoke.py --headless
```

Optional env vars:

- `E2E_BASE_URL` (default `http://34.73.173.191`)
- `E2E_API_URL` (default `https://yapparov-emir-f--gooni-api.modal.run`)
- `E2E_TIMEOUT_MINUTES` (default `8`)
- `E2E_ARTIFACTS_DIR` (default `qa_smoke/artifacts`)

## Output

Each run creates:

- `qa_smoke/artifacts/<timestamp>/SMOKE_REPORT.md`
- screenshots for every completed scenario
- downloaded file artifacts for full-chain generation checks

