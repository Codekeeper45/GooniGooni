# Implementation Plan: Стабильная авторизация и статусы админ-панели

**Branch**: `001-fix-auth-admin-state` | **Date**: 2026-02-26 | **Spec**: `C:\Users\yappa\OneDrive\MyFolder\myProjects\Веб приложение Gooni Gooni\specs\001-fix-auth-admin-state\spec.md`
**Input**: Feature specification from `/specs/001-fix-auth-admin-state/spec.md`

## Summary

Устранить массовые `403` в пользовательском пути генерации, убрав зависимость от ручного `mg_api_key`,
ввести серверно-управляемую сессию генерации (TTL 24 часа без продления), стабилизировать админ-сессию
(истечение после 12 часов неактивности), зафиксировать сервер как единственный источник истины статусов
аккаунтов и закрепить переходы `pending/checking/ready/failed` без ложных откатов в `pending`.

## Technical Context

**Language/Version**: Python 3.11 (backend на Modal), TypeScript + React 18 (frontend)  
**Primary Dependencies**: FastAPI, Modal, Pydantic v2, httpx, React Router, Vite  
**Storage**: Modal Volume `results` (SQLite `gallery.db`), Modal Volume `model-cache`; browser storage только для несекретного UI-состояния  
**Testing**: `pytest backend/tests/`, live API smoke `pytest backend/tests/test_api.py -v --base-url <url> --api-key <key>`, `npm run build`  
**Target Platform**: Modal (API + GPU inference), GCP VM (frontend Docker + Nginx), web browsers  
**Project Type**: web app (frontend + backend inference API)  
**Performance Goals**: 95% запусков генерации без auth-ошибки; админ-переходы без повторного ввода в рамках 12ч idle-window; polling статуса каждые ~3с  
**Constraints**: серверный постоянный секрет не покидает backend; generation session TTL 24ч без refresh; admin session idle-timeout 12ч; сервер-авторитетные статусы аккаунтов  
**Scale/Scope**: 4 активные модели (2 video, 2 image), router с fallback по Modal-аккаунтам, до 3 API-контейнеров и GPU-пул по model type

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Gate

- [x] **Contract Integrity**: Определены изменения контракта auth/session и server-authoritative account status; затронутые зоны: `backend/app.py`, `backend/auth.py`, `backend/admin_security.py`, `src/app/components/MediaGenApp.tsx`, `src/app/admin/*`.
- [x] **Modal Reliability**: Поведение маршрутизации и account statuses задаётся сервером; переходы статусов формализованы; исключаются ложные `ready -> pending`.
- [x] **Security Hygiene**: Постоянный API-секрет остаётся только на сервере; клиент получает ограниченную сессию; политика истечения определена.
- [x] **Test-Gated Delivery**: Заданы обязательные проверки unit/integration/smoke и build-gates.
- [x] **Observability**: Требуются диагностируемые причины auth/health-check ошибок и прозрачные статус-переходы для оператора.

**Gate Result**: PASS

### Post-Design Gate (after Phase 1 artifacts)

- [x] **Contract Integrity**: Контракты зафиксированы в `contracts/api-contracts.md` и отражены в `data-model.md`.
- [x] **Modal Reliability**: FSM статусов аккаунтов и правила fallback закреплены в design-артефактах.
- [x] **Security Hygiene**: Определены session boundaries (24h generation / 12h admin idle), запрет на хранение постоянного секрета в клиенте.
- [x] **Test-Gated Delivery**: В `quickstart.md` зафиксированы проверки на 403-регрессии, статус-переходы и сессионные сценарии.
- [x] **Observability**: Добавлены требования к логам переходов и ошибкам auth/health-check.

**Gate Result**: PASS

## Project Structure

### Documentation (this feature)

```text
specs/001-fix-auth-admin-state/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contracts.md
└── tasks.md
```

### Source Code (repository root)

```text
src/
├── app/
│   ├── components/
│   │   └── MediaGenApp.tsx
│   ├── admin/
│   │   ├── AdminLoginPage.tsx
│   │   ├── AdminDashboard.tsx
│   │   └── adminSession.ts
│   └── routes.tsx
└── styles/

backend/
├── app.py
├── auth.py
├── admin_security.py
├── router.py
├── accounts.py
├── storage.py
├── schemas.py
└── tests/
```

**Structure Decision**: Изменения концентрируются в существующей web-структуре `src/ + backend/` без выделения новых сервисов; контракты и состояния фиксируются в feature-документации.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
