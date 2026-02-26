# Repository Guidelines

## Project Structure & Module Organization
- `src/`: Vite + React frontend application.
- `src/app/`: feature code (`components/`, `pages/`, `context/`, `admin/`, `utils/`).
- `src/styles/`: global styling (`index.css`, `theme.css`, Tailwind entry files).
- `backend/`: Modal-based FastAPI service (`app.py`, `config.py`, `auth.py`, `storage.py`).
- `backend/models/`: model pipeline implementations (`anisora.py`, `phr00t.py`, `pony.py`, `flux.py`).
- `backend/tests/`: pytest suite for API, auth, schemas, router, storage, and config behavior.
- `dist/`: generated frontend build output (do not edit manually).

## Build, Test, and Development Commands
- `npm install`: install frontend dependencies.
- `npm run dev`: start local Vite dev server.
- `npm run build`: create production frontend bundle in `dist/`.
- `pip install -r backend/requirements.txt`: install backend runtime dependencies.
- `pip install pytest httpx`: install test tooling used by backend tests.
- `pytest backend/tests/`: run backend test suite.
- `pytest backend/tests/test_api.py -v --base-url <url> --api-key <key>`: run live API smoke tests.
- `modal serve backend/app.py`: serve backend routes for local route testing.
- `modal deploy backend/app.py`: deploy backend to Modal.

## Coding Style & Naming Conventions
- Frontend (TypeScript/React): use 2-space indentation and functional components.
- Frontend file naming: `PascalCase` for component/page files (for example, `GalleryPage.tsx`), `camelCase` for utility modules (for example, `configManager.ts`).
- Backend (Python): use 4-space indentation and `snake_case` for modules/functions.
- Keep API request/response models centralized in `backend/schemas.py` when extending endpoints.
- No repository-wide lint/formatter config is committed; rely on clean builds and tests before merge.

## Testing Guidelines
- Framework: `pytest` with tests named `test_*.py` under `backend/tests/`.
- Prefer fast unit tests for logic changes; keep integration checks explicit when calling live Modal endpoints.
- For backend changes, update or add tests in the relevant module test file.

## Commit & Pull Request Guidelines
- Follow the existing commit style from history: `type: short imperative summary` (for example, `fix: ...`).
- Keep commits focused to one logical change.
- PRs should include: purpose, linked issue/task, verification steps (`pytest backend/tests/`, `npm run build`), and screenshots for UI/admin changes.

## Security & Configuration Tips
- Do not commit secrets. Use `.env.example` as the template for local env files.
- Keep runtime secrets in Modal secrets (`gooni-api-key`, `gooni-admin`, and `huggingface` when needed).
