# HTTP API Contract (MUST Baseline)

## Scope

Public and admin API contracts required by `spec.md` for the MUST baseline.
This document defines target contract behavior and key compatibility notes.

## Authentication Policy

- Generation/media precedence: `X-API-Key` -> `api_key` query -> `gg_session` cookie fallback.
- UI flow primary auth: session cookie (`gg_session`).
- Admin bootstrap: `POST /admin/session` with `x-admin-key` only.
- Admin protected routes: admin session required.

## Endpoints

### Session

#### `POST /auth/session`
- Auth: none
- Success: `204`
- Side effects: issue `gg_session` cookie + persist active session

#### `GET /auth/session`
- Auth: `gg_session`
- Success: `200 { valid: boolean, expires_at: string }`
- Failure: `401` structured error

#### `DELETE /auth/session`
- Auth: `gg_session`
- Success: `204`
- Side effects: revoke session

### Generation

#### `POST /generate`
- Auth: per precedence policy
- Request: model/type/mode/prompt + params
- Success: `200 { task_id: string }`
- Failure: `422`, `403`, `503` structured errors
- Guarantees: task persisted before async dispatch

#### `GET /status/{task_id}`
- Auth: per precedence policy
- Success: `200 { status, progress, error_msg? }`
- Failure: `404`, auth errors
- Status domain: `pending|processing|done|failed`

#### `GET /results/{task_id}`
- Auth: per precedence policy (query-compatible for browser media)
- Success: `200` file stream (`video/mp4`, `image/png`, `image/jpeg`)
- Failure: `404|410|403`

#### `GET /preview/{task_id}`
- Auth: per precedence policy
- Success: `200` preview image stream
- Failure: `404|403`

### Gallery

#### `GET /gallery`
- Auth: per precedence policy
- Success: `200` array of done-task projections (newest first)

#### `DELETE /gallery/{task_id}`
- Auth: per precedence policy
- Success: `204`
- Failure: `404|403`

### Health

#### `GET /health`
- Auth: none
- Success: `200 { ok: true }`

#### `GET /admin/health`
- Auth: admin session
- Success: `200` aggregated storage/account/volume status

### Admin

#### `POST /admin/session`
- Auth: `x-admin-key`
- Success: admin session established

#### `GET /admin/logs`
- Auth: admin session
- Success: audit event list

#### `/admin/accounts*`
- Auth: admin session
- Behavior: account CRUD + deploy trigger + health/state management

## Error Contract

All non-2xx responses MUST follow:

```json
{
  "code": "machine_readable_code",
  "detail": "Human-readable message",
  "user_action": "Action guidance"
}
```

## Compatibility Notes (As-Is -> Target)

1. `spec.md` references `src/app/api/sessionClient.ts`; active code uses `src/app/utils/sessionClient.ts`.
2. Model label drift (`wan-remix` naming vs internal `phr00t`) requires canonical mapping doc in backend config + frontend model metadata.
3. Gallery currently has localStorage-first UX path; target contract keeps `/gallery` as authoritative server contract for shared consistency.

## Security Notes

- No admin credentials in query params.
- CORS must use explicit allowlist for production.
- Proxy routing for remote workspace tasks must validate target workspace identity before forwarding.

## Contract-to-Code Mapping (Primary)

- Backend: `backend/app.py`, `backend/auth.py`, `backend/schemas.py`, `backend/storage.py`, `backend/admin_security.py`, `backend/router.py`
- Frontend: `src/app/components/MediaGenApp.tsx`, `src/app/components/OutputPanel.tsx`, `src/app/context/GalleryContext.tsx`, `src/app/utils/sessionClient.ts`, `src/app/admin/*`
