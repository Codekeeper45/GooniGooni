# API Contracts: Стабильная авторизация и статусы админ-панели

## Contract Goals

- Пользователь запускает генерацию без ручного `X-API-Key`.
- Постоянный backend секрет не покидает сервер.
- Статусы аккаунтов в admin читаются только с сервера.
- Политики сессий: generation 24h fixed TTL, admin 12h idle timeout.

## 1) Generation Session Contracts

### POST `/auth/session`

Назначение: выдать клиентскую generation-сессию.

- **Request**: без тела.
- **Response**: `201 Created`
  - body:
    - `session_status`: `active`
    - `expires_at`: ISO datetime
  - cookie:
    - `gg_session=<token>`
    - `HttpOnly`, `Secure`, `SameSite=Strict`, `Max-Age=86400`
- **Errors**:
  - `429` rate-limited
  - `503` session issuance unavailable

### GET `/auth/session`

Назначение: проверить состояние generation-сессии.

- **Response**: `200 OK`
  - `active: true|false`
  - `expires_at` (if active)
- **Errors**:
  - `401` missing/expired/revoked session

## 2) Generation API Auth Boundary (updated)

### Protected by generation session cookie

- `POST /generate`
- `GET /status/{task_id}`
- `GET /results/{task_id}`
- `GET /preview/{task_id}`
- `GET /gallery`
- `DELETE /gallery/{task_id}`

### Server-to-server compatibility

- Internal inter-workspace proxy calls MAY continue using `X-API-Key`.
- Browser path MUST NOT require manual `X-API-Key` input.

### Error Contract

- `401 Unauthorized`: session missing/expired/revoked.
- `403 Forbidden`: request authenticated but forbidden by policy.
- Error body MUST include user-actionable `detail`.

## 3) Admin Session Contracts

### POST `/admin/session`

Назначение: создать admin-сессию после проверки admin key.

- **Request**:
  - header `x-admin-key: <key>`
- **Response**: `204 No Content`
  - cookie:
    - `gg_admin_session=<token>`
    - `HttpOnly`, `Secure`, `SameSite=Strict`
- **Session policy**:
  - expires on 12h inactivity

### GET `/admin/session`

Назначение: проверка активной admin-сессии для SPA bootstrap.

- **Response**: `200 OK`
  - `active: true`
  - `idle_timeout_seconds: 43200`
- **Errors**:
  - `401` no valid admin session

### DELETE `/admin/session`

Назначение: logout и revoke active admin session.

- **Response**: `204 No Content`

## 4) Admin Accounts Status Contract (updated)

### GET `/admin/accounts`

- **Response**: `200 OK`
  - `accounts[]` includes:
    - `id`, `label`, `workspace`, `status`, `use_count`, `last_used`, `last_error`, `added_at`

### Allowed status values

- `pending`, `checking`, `ready`, `failed`, `disabled`

### Status semantics

- `ready` only after successful health-check.
- Failed health-check MUST surface as `failed`.
- Client MUST treat this endpoint as authoritative source of status.

## 5) Status Transition Contract

### Required transitions

- `pending -> checking`
- `checking -> ready`
- `checking -> failed`
- `failed -> checking` (manual retry)
- `ready -> checking` (manual redeploy/recheck)

### Forbidden transitions

- `ready -> pending` (except explicit account recreation/credential reset event)
- `failed -> ready` without `checking`

## 6) Backward Compatibility Notes

- Existing response fields for generation status/results remain, but auth mechanism for browser clients moves from manual key to cookie session.
- Transition window MAY support both mechanisms temporarily; final target is zero manual key entry for end users.
