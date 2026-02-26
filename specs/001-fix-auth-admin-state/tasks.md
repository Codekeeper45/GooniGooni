# Tasks: РЎС‚Р°Р±РёР»СЊРЅР°СЏ Р°РІС‚РѕСЂРёР·Р°С†РёСЏ Рё СЃС‚Р°С‚СѓСЃС‹ Р°РґРјРёРЅ-РїР°РЅРµР»Рё

**Input**: Design documents from `/specs/001-fix-auth-admin-state/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/, quickstart.md

**Tests**: РўРµСЃС‚С‹ РІРєР»СЋС‡РµРЅС‹, С‚Р°Рє РєР°Рє РІ РїР»Р°РЅРµ Рё quickstart Р·Р°С„РёРєСЃРёСЂРѕРІР°РЅС‹ РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Рµ РїСЂРѕРІРµСЂРєРё (`pytest backend/tests/`, live API smoke, `npm run build`).

**Organization**: Р—Р°РґР°С‡Рё СЃРіСЂСѓРїРїРёСЂРѕРІР°РЅС‹ РїРѕ user story С‚Р°Рє, С‡С‚РѕР±С‹ РєР°Р¶РґСѓСЋ РёСЃС‚РѕСЂРёСЋ РјРѕР¶РЅРѕ Р±С‹Р»Рѕ СЂРµР°Р»РёР·РѕРІР°С‚СЊ Рё РїСЂРѕРІРµСЂРёС‚СЊ РЅРµР·Р°РІРёСЃРёРјРѕ.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: РјРѕР¶РЅРѕ РІС‹РїРѕР»РЅСЏС‚СЊ РїР°СЂР°Р»Р»РµР»СЊРЅРѕ (СЂР°Р·РЅС‹Рµ С„Р°Р№Р»С‹, РЅРµС‚ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё РѕС‚ РЅРµР·Р°РІРµСЂС€С‘РЅРЅС‹С… Р·Р°РґР°С‡)
- **[Story]**: `US1`, `US2`, `US3` РґР»СЏ Р·Р°РґР°С‡ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёС… РёСЃС‚РѕСЂРёР№
- РљР°Р¶РґР°СЏ Р·Р°РґР°С‡Р° СЃРѕРґРµСЂР¶РёС‚ С‚РѕС‡РЅС‹Р№ РїСѓС‚СЊ Рє С„Р°Р№Р»Сѓ

## Path Conventions

- Frontend: `src/app/components/`, `src/app/admin/`, `src/app/utils/`, `src/app/routes.tsx`
- Backend: `backend/app.py`, `backend/auth.py`, `backend/admin_security.py`, `backend/accounts.py`, `backend/deployer.py`, `backend/storage.py`, `backend/schemas.py`, `backend/tests/`
- Feature docs: `specs/001-fix-auth-admin-state/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: РџРѕРґРіРѕС‚РѕРІРёС‚СЊ РѕРєСЂСѓР¶РµРЅРёРµ Рё Р·Р°С„РёРєСЃРёСЂРѕРІР°С‚СЊ РїР°СЂР°РјРµС‚СЂС‹ С„РёС‡Рё РґРѕ РёР·РјРµРЅРµРЅРёСЏ runtime-РїРѕРІРµРґРµРЅРёСЏ.

- [X] T001 Р—Р°С„РёРєСЃРёСЂРѕРІР°С‚СЊ baseline РїРѕРІРµРґРµРЅРёСЏ auth/status РІ `specs/001-fix-auth-admin-state/research.md`
- [X] T002 РћР±РЅРѕРІРёС‚СЊ РїРµСЂРµРјРµРЅРЅС‹Рµ РѕРєСЂСѓР¶РµРЅРёСЏ РґР»СЏ session policy РІ `.env.example`
- [X] T003 [P] РџРѕРґРіРѕС‚РѕРІРёС‚СЊ РѕР±С‰РёР№ frontend session client РІ `src/app/utils/sessionClient.ts`
- [X] T004 [P] РџРѕРґРіРѕС‚РѕРІРёС‚СЊ backend С‚РµСЃС‚РѕРІС‹Рµ С„РёРєСЃС‚СѓСЂС‹ РґР»СЏ session/cookie СЃС†РµРЅР°СЂРёРµРІ РІ `backend/tests/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Р‘Р»РѕРєРёСЂСѓСЋС‰Р°СЏ РёРЅС„СЂР°СЃС‚СЂСѓРєС‚СѓСЂР° auth/session/FSM РїРµСЂРµРґ СЂРµР°Р»РёР·Р°С†РёРµР№ user stories.

- [X] T005 Р”РѕР±Р°РІРёС‚СЊ РјРѕРґРµР»Рё session/FSM РѕС‚РІРµС‚РѕРІ Рё РІР°Р»РёРґР°С†РёРё РІ `backend/schemas.py`
- [X] T006 Р”РѕР±Р°РІРёС‚СЊ С…СЂР°РЅРµРЅРёРµ session state (generation/admin) РІ `backend/storage.py`
- [X] T007 Р РµР°Р»РёР·РѕРІР°С‚СЊ middleware/dependencies РґР»СЏ generation session РІ `backend/auth.py`
- [X] T008 Р РµР°Р»РёР·РѕРІР°С‚СЊ admin session validation Рё idle-timeout РєРѕРЅС‚СЂРѕР»СЊ РІ `backend/admin_security.py`
- [X] T009 Р’РІРµСЃС‚Рё guard-РїСЂР°РІРёР»Р° РїРµСЂРµС…РѕРґРѕРІ СЃС‚Р°С‚СѓСЃРѕРІ Р°РєРєР°СѓРЅС‚РѕРІ РІ `backend/accounts.py`
- [X] T010 РћР±РЅРѕРІРёС‚СЊ deploy lifecycle РЅР° `pending -> checking -> ready|failed` РІ `backend/deployer.py`
- [X] T011 РЎРёРЅС…СЂРѕРЅРёР·РёСЂРѕРІР°С‚СЊ CORS/cookie/session wiring Рё volume reload С‚РѕС‡РєРё РІ `backend/app.py`
- [X] T012 [P] Р”РѕР±Р°РІРёС‚СЊ Р±Р°Р·РѕРІС‹Рµ С‚РµСЃС‚С‹ РґР»СЏ session/FSM РёРЅС„СЂР°СЃС‚СЂСѓРєС‚СѓСЂС‹ РІ `backend/tests/test_auth.py` Рё `backend/tests/test_accounts.py`

**Checkpoint**: РџРѕСЃР»Рµ Р·Р°РІРµСЂС€РµРЅРёСЏ Phase 2 РјРѕР¶РЅРѕ СЂРµР°Р»РёР·РѕРІС‹РІР°С‚СЊ user stories РЅРµР·Р°РІРёСЃРёРјРѕ.

---

## Phase 3: User Story 1 - РЈСЃРїРµС€РЅР°СЏ РіРµРЅРµСЂР°С†РёСЏ Р±РµР· СЂСѓС‡РЅРѕРіРѕ РєР»СЋС‡Р° (Priority: P1)

**Goal**: РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ Р·Р°РїСѓСЃРєР°РµС‚ РіРµРЅРµСЂР°С†РёСЋ Р±РµР· СЂСѓС‡РЅРѕРіРѕ РІРІРѕРґР° API key Рё Р±РµР· 403 РІ С‚РёРїРѕРІРѕРј РїРѕС‚РѕРєРµ.

**Independent Test**: РћС‚РєСЂС‹С‚СЊ UI Р±РµР· `localStorage.mg_api_key`, Р·Р°РїСѓСЃС‚РёС‚СЊ РіРµРЅРµСЂР°С†РёСЋ, РїРѕР»СѓС‡РёС‚СЊ task Рё СЂРµР·СѓР»СЊС‚Р°С‚ Р±РµР· auth-РѕС€РёР±РѕРє.

### Tests for User Story 1

- [X] T013 [P] [US1] Р”РѕР±Р°РІРёС‚СЊ РєРѕРЅС‚СЂР°РєС‚РЅС‹Рµ С‚РµСЃС‚С‹ `/auth/session` Рё generation auth boundary РІ `backend/tests/test_api.py`
- [X] T014 [P] [US1] Р”РѕР±Р°РІРёС‚СЊ РёРЅС‚РµРіСЂР°С†РёРѕРЅРЅС‹Р№ С‚РµСЃС‚ РіРµРЅРµСЂР°С†РёРё Р±РµР· СЂСѓС‡РЅРѕРіРѕ `X-API-Key` РІ `backend/tests/test_api.py`

### Implementation for User Story 1

- [X] T015 [US1] Р”РѕР±Р°РІРёС‚СЊ endpoints `POST /auth/session` Рё `GET /auth/session` РІ `backend/app.py`
- [X] T016 [US1] РџРµСЂРµРІРµСЃС‚Рё `/generate`, `/status/{task_id}`, `/results/{task_id}`, `/preview/{task_id}`, `/gallery` РЅР° generation session dependency РІ `backend/app.py` Рё `backend/auth.py`
- [X] T017 [P] [US1] РћР±РЅРѕРІРёС‚СЊ РєР»РёРµРЅС‚СЃРєРёР№ Р·Р°РїСѓСЃРє РіРµРЅРµСЂР°С†РёРё Рё bootstrap session Р±РµР· `mg_api_key` РІ `src/app/components/MediaGenApp.tsx`
- [X] T018 [US1] РћР±РЅРѕРІРёС‚СЊ РїРѕР»СѓС‡РµРЅРёРµ РјРµРґРёР°-СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ РїРѕРґ cookie-auth РІ `src/app/components/OutputPanel.tsx`
- [X] T019 [US1] Р”РѕР±Р°РІРёС‚СЊ UX-РѕР±СЂР°Р±РѕС‚РєСѓ РёСЃС‚С‘РєС€РµР№ generation session (re-auth/retry) РІ `src/app/components/MediaGenApp.tsx`

**Checkpoint**: US1 СЂР°Р±РѕС‚Р°РµС‚ РЅРµР·Р°РІРёСЃРёРјРѕ Рё СѓСЃС‚СЂР°РЅСЏРµС‚ РјР°СЃСЃРѕРІС‹Рµ 403 РЅР° РіРµРЅРµСЂР°С†РёРё.

---

## Phase 4: User Story 2 - Р”РѕСЃС‚РѕРІРµСЂРЅС‹Рµ СЃС‚Р°С‚СѓСЃС‹ Р°РєРєР°СѓРЅС‚РѕРІ РІ Admin (Priority: P1)

**Goal**: РђРґРјРёРЅ РІРёРґРёС‚ РєРѕСЂСЂРµРєС‚РЅС‹Рµ СЃРµСЂРІРµСЂРЅС‹Рµ СЃС‚Р°С‚СѓСЃС‹ Р±РµР· Р»РѕР¶РЅРѕРіРѕ reset РІ `pending`.

**Independent Test**: РџРѕСЃР»Рµ СѓСЃРїРµС€РЅРѕРіРѕ health-check Р°РєРєР°СѓРЅС‚ РѕСЃС‚Р°С‘С‚СЃСЏ `ready` РїСЂРё РїРѕРІС‚РѕСЂРЅРѕРј РѕС‚РєСЂС‹С‚РёРё РїР°РЅРµР»Рё; РїСЂРё РїСЂРѕРІР°Р»Рµ health-check СЃС‚Р°РЅРѕРІРёС‚СЃСЏ `failed`.

### Tests for User Story 2

- [X] T020 [P] [US2] Р”РѕР±Р°РІРёС‚СЊ С‚РµСЃС‚С‹ FSM-РїРµСЂРµС…РѕРґРѕРІ Рё forbidden transitions РІ `backend/tests/test_accounts.py`
- [X] T021 [P] [US2] Р”РѕР±Р°РІРёС‚СЊ API-С‚РµСЃС‚ server-authoritative СЃС‚Р°С‚СѓСЃРѕРІ `/admin/accounts` РІ `backend/tests/test_api.py`

### Implementation for User Story 2

- [X] T022 [US2] РћР±РЅРѕРІРёС‚СЊ СЃРµСЂРІРµСЂРЅС‹Рµ РїРµСЂРµС…РѕРґС‹ СЃС‚Р°С‚СѓСЃРѕРІ deploy/health-check РІ `backend/deployer.py`
- [X] T023 [US2] Р”РѕР±Р°РІРёС‚СЊ СЏРІРЅС‹Р№ `checking` Рё Р·Р°РїСЂРµС‚ `ready -> pending` Р±РµР· СЃРѕР±С‹С‚РёСЏ РїРµСЂРµСЃРѕР·РґР°РЅРёСЏ РІ `backend/accounts.py`
- [X] T024 [US2] РћР±РЅРѕРІРёС‚СЊ admin deploy endpoints СЃ РєРѕСЂСЂРµРєС‚РЅС‹РјРё reload/commit С‚РѕС‡РєР°РјРё РІ `backend/app.py`
- [X] T025 [US2] РћР±РЅРѕРІРёС‚СЊ fallback/РѕС€РёР±РєРё СЂРѕСѓС‚РµСЂР° РґР»СЏ failed-Р°РєРєР°СѓРЅС‚РѕРІ РІ `backend/router.py`
- [X] T026 [P] [US2] РЈРґР°Р»РёС‚СЊ Р»РѕРєР°Р»СЊРЅС‹Рµ РїРµСЂРµРѕРїСЂРµРґРµР»РµРЅРёСЏ СЃС‚Р°С‚СѓСЃРѕРІ РІ UI Рё СЂРµРЅРґРµСЂРёС‚СЊ С‚РѕР»СЊРєРѕ СЃРµСЂРІРµСЂРЅС‹Рµ Р·РЅР°С‡РµРЅРёСЏ РІ `src/app/admin/AdminDashboard.tsx`
- [X] T027 [US2] Р РµР°Р»РёР·РѕРІР°С‚СЊ structured logging РїРµСЂРµС…РѕРґРѕРІ СЃС‚Р°С‚СѓСЃРѕРІ (prev/new/reason) РІ `backend/accounts.py` Рё `backend/deployer.py`
- [X] T028 [P] [US2] Р”РѕР±Р°РІРёС‚СЊ С‚РµСЃС‚С‹ Р»РѕРіРёСЂРѕРІР°РЅРёСЏ РїРµСЂРµС…РѕРґРѕРІ СЃС‚Р°С‚СѓСЃРѕРІ РІ `backend/tests/test_accounts.py`

**Checkpoint**: US2 РЅРµР·Р°РІРёСЃРёРјРѕ РѕР±РµСЃРїРµС‡РёРІР°РµС‚ РґРѕСЃС‚РѕРІРµСЂРЅС‹Рµ СЃС‚Р°С‚СѓСЃС‹ Рё СЃС‚Р°Р±РёР»СЊРЅСѓСЋ РѕРїРµСЂР°С†РёРѕРЅРЅСѓСЋ РєР°СЂС‚РёРЅСѓ.

---

## Phase 5: User Story 3 - РЎРѕС…СЂР°РЅРµРЅРёРµ Р°РґРјРёРЅ-РґРѕСЃС‚СѓРїР° РјРµР¶РґСѓ СЃРµСЃСЃРёСЏРјРё (Priority: P2)

**Goal**: РђРґРјРёРЅ РЅРµ С‚РµСЂСЏРµС‚ РІС…РѕРґ РїСЂРё РѕР±С‹С‡РЅС‹С… РїРѕРІС‚РѕСЂРЅС‹С… Р·Р°С…РѕРґР°С…, РЅРѕ РїРµСЂРµР°РІС‚РѕСЂРёР·СѓРµС‚СЃСЏ РїРѕСЃР»Рµ 12 С‡Р°СЃРѕРІ РЅРµР°РєС‚РёРІРЅРѕСЃС‚Рё.

**Independent Test**: РџРѕРІС‚РѕСЂРЅС‹Р№ Р·Р°С…РѕРґ РІ Р°РґРјРёРЅРєСѓ РІ РїСЂРµРґРµР»Р°С… idle-window РЅРµ С‚СЂРµР±СѓРµС‚ РІРІРѕРґР° РєР»СЋС‡Р°; РїРѕСЃР»Рµ idle-timeout Р·Р°РїСЂР°С€РёРІР°РµС‚СЃСЏ РїРѕРІС‚РѕСЂРЅС‹Р№ РІС…РѕРґ.

### Tests for User Story 3

- [X] T029 [P] [US3] Р”РѕР±Р°РІРёС‚СЊ С‚РµСЃС‚С‹ idle-timeout 12h РґР»СЏ admin session РІ `backend/tests/test_auth.py` Рё `backend/tests/test_api.py`
- [X] T030 [P] [US3] Р”РѕР±Р°РІРёС‚СЊ С‚РµСЃС‚С‹ admin session endpoints (`POST/GET/DELETE /admin/session`) РІ `backend/tests/test_api.py`
- [X] T031 [P] [US3] Р”РѕР±Р°РІРёС‚СЊ С‚РµСЃС‚С‹ Р·Р°РїРёСЃРё Р°СѓРґРёС‚Р° РґР»СЏ admin session endpoints РІ `backend/tests/test_api.py`

### Implementation for User Story 3

- [X] T032 [US3] Р”РѕР±Р°РІРёС‚СЊ endpoints admin session (`POST/GET/DELETE /admin/session`) РІ `backend/app.py`
- [X] T033 [US3] Р РµР°Р»РёР·РѕРІР°С‚СЊ РѕР±РЅРѕРІР»РµРЅРёРµ `last_activity` Рё РёСЃС‚РµС‡РµРЅРёРµ admin session РІ `backend/admin_security.py` Рё `backend/storage.py`
- [X] T034 [US3] Р”РѕР±Р°РІРёС‚СЊ Р°СѓРґРёС‚ РґРµР№СЃС‚РІРёР№ `POST/GET/DELETE /admin/session` РІ `backend/app.py` Рё `backend/admin_security.py`
- [X] T035 [P] [US3] РџРµСЂРµРІРµСЃС‚Рё frontend admin auth c `sessionStorage` key РЅР° cookie-session bootstrap РІ `src/app/admin/adminSession.ts` Рё `src/app/admin/AdminLoginPage.tsx`
- [X] T036 [US3] РћР±РЅРѕРІРёС‚СЊ guard/redirect Рё СЃРѕРѕР±С‰РµРЅРёРµ РѕР± РёСЃС‚РµРєС€РµР№ СЃРµСЃСЃРёРё РІ `src/app/admin/AdminDashboard.tsx` Рё `src/app/routes.tsx`

**Checkpoint**: US3 РЅРµР·Р°РІРёСЃРёРјРѕ Р·Р°РєСЂС‹РІР°РµС‚ РїСЂРѕР±Р»РµРјСѓ РїСЂРѕРїР°РґР°СЋС‰РµРіРѕ admin key Рё РґРѕР»РіРѕР№ РїРѕРІС‚РѕСЂРЅРѕР№ Р°РІС‚РѕСЂРёР·Р°С†РёРё.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Р¤РёРЅР°Р»СЊРЅР°СЏ СЃС‚Р°Р±РёР»РёР·Р°С†РёСЏ, РґРѕРєСѓРјРµРЅС‚Р°С†РёСЏ Рё РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Рµ РїСЂРѕРІРµСЂРєРё СЂРµР»РёР·РЅРѕР№ РіРѕС‚РѕРІРЅРѕСЃС‚Рё.

- [X] T037 [P] РћР±РЅРѕРІРёС‚СЊ СЌРєСЃРїР»СѓР°С‚Р°С†РёРѕРЅРЅС‹Рµ РґРѕРєСѓРјРµРЅС‚С‹ РїРѕ РЅРѕРІРѕР№ auth/session РјРѕРґРµР»Рё РІ `API_INTEGRATION_GUIDE.md` Рё `TESTING_GUIDE_RU.md`
- [ ] T038 Р’С‹РїРѕР»РЅРёС‚СЊ Рё Р·Р°С„РёРєСЃРёСЂРѕРІР°С‚СЊ backend test suite `pytest backend/tests/` РІ `specs/001-fix-auth-admin-state/quickstart.md`
- [ ] T039 Р’С‹РїРѕР»РЅРёС‚СЊ Рё Р·Р°С„РёРєСЃРёСЂРѕРІР°С‚СЊ frontend build `npm run build` РІ `specs/001-fix-auth-admin-state/quickstart.md`
- [ ] T040 Р’С‹РїРѕР»РЅРёС‚СЊ live smoke `pytest backend/tests/test_api.py -v --base-url <url> --api-key <key>` Рё Р·Р°РЅРµСЃС‚Рё СЂРµР·СѓР»СЊС‚Р°С‚С‹ РІ `specs/001-fix-auth-admin-state/quickstart.md`
- [X] T041 [P] РџСЂРѕРІРµСЂРёС‚СЊ РѕС‚СЃСѓС‚СЃС‚РІРёРµ С…СЂР°РЅРµРЅРёСЏ РїРѕСЃС‚РѕСЏРЅРЅС‹С… СЃРµРєСЂРµС‚РѕРІ С‡РµСЂРµР· РїСЂРѕРІРµСЂРєРё РІ `src/app/components/MediaGenApp.tsx`, `src/app/admin/adminSession.ts` Рё `src/app/utils/sessionClient.ts`
- [X] T042 [P] Р”РѕР±Р°РІРёС‚СЊ API-С‚РµСЃС‚ CORS allowlist/preflight РґР»СЏ С†РµР»РµРІРѕРіРѕ frontend origin РІ `backend/tests/test_api.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: СЃС‚Р°СЂС‚ СЃСЂР°Р·Сѓ.
- **Phase 2 (Foundational)**: Р·Р°РІРёСЃРёС‚ РѕС‚ Setup; Р±Р»РѕРєРёСЂСѓРµС‚ user stories.
- **Phase 3/4/5 (US1/US2/US3)**: СЃС‚Р°СЂС‚СѓСЋС‚ РїРѕСЃР»Рµ Р·Р°РІРµСЂС€РµРЅРёСЏ Foundational.
- **Phase 6 (Polish)**: РїРѕСЃР»Рµ Р·Р°РІРµСЂС€РµРЅРёСЏ РІС‹Р±СЂР°РЅРЅС‹С… user stories.

### User Story Dependencies

- **US1 (P1)**: Р·Р°РІРёСЃРёС‚ С‚РѕР»СЊРєРѕ РѕС‚ Phase 2.
- **US2 (P1)**: Р·Р°РІРёСЃРёС‚ С‚РѕР»СЊРєРѕ РѕС‚ Phase 2.
- **US3 (P2)**: Р·Р°РІРёСЃРёС‚ С‚РѕР»СЊРєРѕ РѕС‚ Phase 2.
- РСЃС‚РѕСЂРёРё РјРѕРіСѓС‚ РёРґС‚Рё РїР°СЂР°Р»Р»РµР»СЊРЅРѕ РїРѕСЃР»Рµ Foundational РїСЂРё РґРѕСЃС‚Р°С‚РѕС‡РЅРѕР№ РєРѕРјР°РЅРґРµ.

### Dependency Graph

- Setup -> Foundational -> (US1 || US2 || US3) -> Polish
- MVP РїСѓС‚СЊ: Setup -> Foundational -> US1 -> Polish

### Within Each User Story

- РЎРЅР°С‡Р°Р»Р° С‚РµСЃС‚С‹ РёСЃС‚РѕСЂРёРё, Р·Р°С‚РµРј backend РєРѕРЅС‚СЂР°РєС‚/Р»РѕРіРёРєР°, Р·Р°С‚РµРј frontend РёРЅС‚РµРіСЂР°С†РёСЏ, Р·Р°С‚РµРј smoke.
- РСЃС‚РѕСЂРёСЏ СЃС‡РёС‚Р°РµС‚СЃСЏ Р·Р°РІРµСЂС€С‘РЅРЅРѕР№ С‚РѕР»СЊРєРѕ РїРѕСЃР»Рµ РїСЂРѕС…РѕР¶РґРµРЅРёСЏ РµС‘ Independent Test.

---

## Parallel Execution Examples

### User Story 1

```bash
# РџР°СЂР°Р»Р»РµР»СЊРЅРѕ РїРѕСЃР»Рµ T016:
Task T017 [US1] in src/app/components/MediaGenApp.tsx
Task T018 [US1] in src/app/components/OutputPanel.tsx
```

### User Story 2

```bash
# РџР°СЂР°Р»Р»РµР»СЊРЅРѕ РїРѕСЃР»Рµ T024:
Task T025 [US2] in backend/router.py
Task T026 [US2] in src/app/admin/AdminDashboard.tsx
```

### User Story 3

```bash
# РџР°СЂР°Р»Р»РµР»СЊРЅРѕ РїРѕСЃР»Рµ T034:
Task T035 [US3] in src/app/admin/adminSession.ts + AdminLoginPage.tsx
Task T036 [US3] in src/app/admin/AdminDashboard.tsx + src/app/routes.tsx
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Р—Р°РІРµСЂС€РёС‚СЊ Phase 1 Рё Phase 2.
2. Р РµР°Р»РёР·РѕРІР°С‚СЊ US1 (Phase 3).
3. РџСЂРѕРіРЅР°С‚СЊ РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Рµ РїСЂРѕРІРµСЂРєРё РёР· Phase 6 (T038-T040).
4. РџРѕРєР°Р·Р°С‚СЊ СЂРµР·СѓР»СЊС‚Р°С‚: РіРµРЅРµСЂР°С†РёСЏ Р±РµР· СЂСѓС‡РЅРѕРіРѕ API key Рё Р±РµР· 403.

### Incremental Delivery

1. MVP: US1.
2. РћРїРµСЂР°С†РёРѕРЅРЅР°СЏ СЃС‚Р°Р±РёР»СЊРЅРѕСЃС‚СЊ: US2.
3. РђРґРјРёРЅ-UX Рё Р±РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ СЃРµСЃСЃРёРё: US3.
4. Р¤РёРЅР°Р»СЊРЅС‹Р№ polish Рё smoke-РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ.

### Parallel Team Strategy

1. РљРѕРјР°РЅРґР° СЃРѕРІРјРµСЃС‚РЅРѕ Р·Р°РєСЂС‹РІР°РµС‚ Setup + Foundational.
2. РџРѕСЃР»Рµ СЌС‚РѕРіРѕ:
   - Р Р°Р·СЂР°Р±РѕС‚С‡РёРє A: US1
   - Р Р°Р·СЂР°Р±РѕС‚С‡РёРє B: US2
   - Р Р°Р·СЂР°Р±РѕС‚С‡РёРє C: US3
3. РРЅС‚РµРіСЂР°С†РёСЏ Рё С„РёРЅР°Р»СЊРЅР°СЏ РІР°Р»РёРґР°С†РёСЏ РІ Polish.

---

## Notes

- Р’СЃРµ Р·Р°РґР°С‡Рё СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓСЋС‚ С„РѕСЂРјР°С‚Сѓ checklist: `- [ ] T### [P] [US#] Description with file path`.
- `[US#]` РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ С‚РѕР»СЊРєРѕ РІ story phases.
- `[P]` РїСЂРѕСЃС‚Р°РІР»РµРЅ С‚РѕР»СЊРєРѕ РґР»СЏ Р·Р°РґР°С‡, СЂРµР°Р»СЊРЅРѕ РЅРµР·Р°РІРёСЃРёРјС‹С… РїРѕ С„Р°Р№Р»Р°Рј/Р·Р°РІРёСЃРёРјРѕСЃС‚СЏРј.
- РљР°Р¶РґР°СЏ user story РёРјРµРµС‚ СЃРѕР±СЃС‚РІРµРЅРЅС‹Р№ РЅРµР·Р°РІРёСЃРёРјС‹Р№ РєСЂРёС‚РµСЂРёР№ РїСЂРѕРІРµСЂРєРё.



