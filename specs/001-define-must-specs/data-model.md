# Data Model: MUST Inference Platform Baseline

## 1) Task

**Purpose**: Represents one generation request lifecycle from submission to terminal state.

**Fields**
- `id` (string, unique)
- `workspace` (string, nullable; routing namespace for remote execution)
- `model` (enum: `anisora`, `phr00t`, `pony`, `flux`)
- `type` (enum: `video`, `image`)
- `mode` (string; model-dependent)
- `prompt` (string, required)
- `negative_prompt` (string, optional)
- `parameters` (object/json; validated against config schema)
- `seed` (integer)
- `status` (enum: `pending`, `processing`, `done`, `failed`)
- `progress` (integer 0..100)
- `result_path` (string, nullable)
- `preview_path` (string, nullable)
- `error_msg` (string, nullable)
- `created_at` (datetime)
- `updated_at` (datetime)
- `started_at` (datetime, nullable)
- `finished_at` (datetime, nullable)

**Validation rules**
- `status` transitions are monotonic for one run: `pending -> processing -> done|failed`.
- `result_path` required when `status=done`.
- `error_msg` required when `status=failed`.
- stale policy for `processing`:
  - image task runtime >10 min => transition to `failed`
  - video task runtime >30 min => transition to `failed`

## 2) GenerationSession

**Purpose**: Auth session for UI users.

**Fields**
- `token` (string, unique, secure random)
- `status` (enum: `active`, `revoked`, `expired`)
- `issued_at` (datetime)
- `expires_at` (datetime)
- `client_context` (string, optional: IP / fingerprint hint)
- `revoked_at` (datetime, nullable)

**Validation rules**
- session validity requires `status=active` and `expires_at > now`.
- revocation is terminal for token.

## 3) WorkerAccount

**Purpose**: Dispatch target for account-router in multi-workspace execution.

**Fields**
- `workspace` (string, unique)
- `status` (enum: `pending`, `ready`, `failed`, `disabled`)
- `modal_token_id` (string, encrypted-at-rest or protected secret reference)
- `modal_token_secret` (string, encrypted-at-rest)
- `last_health_at` (datetime, nullable)
- `last_health_status` (enum/string)
- `last_error` (string, nullable)
- `created_at` (datetime)
- `updated_at` (datetime)

**Validation rules**
- successful health check transitions account to `ready`.
- account state must persist across admin page reload/navigation.
- `disabled` accounts are excluded from dispatch.

## 4) AdminSession

**Purpose**: Authenticated admin context after bootstrap.

**Fields**
- `token` (string, unique)
- `issued_at` (datetime)
- `expires_at` (datetime)
- `last_activity_at` (datetime)
- `status` (enum: `active`, `expired`, `revoked`)

**Validation rules**
- bootstrap uses `x-admin-key`.
- protected admin routes require valid admin session.

## 5) AdminAuditEvent

**Purpose**: Immutable audit record for security/admin-sensitive operations.

**Fields**
- `id` (integer/uuid, unique)
- `ts` (datetime)
- `actor_type` (enum: `admin`, `system`)
- `actor_id` (string, nullable)
- `ip` (string, nullable)
- `action` (string)
- `target` (string, nullable)
- `details` (object/string)
- `success` (boolean)

**Validation rules**
- each admin-sensitive action writes one audit event.
- both successful and failed attempts are logged.

## 6) ModelConfigurationEntry

**Purpose**: Source-of-truth description of model capabilities and parameter constraints.

**Fields**
- `catalog_version` (string)
- `family` (enum: image/video groups)
- `model_id` (string)
- `type` (enum: `image`, `video`)
- `modes` (array/object)
- `parameters` (object: types, defaults, min/max, visibility, dependencies)
- `recommended_resolutions` (array)

**Validation rules**
- frontend form behavior must derive from this entry.
- backend validation/dispatch must align with this entry.

## Relationships

- `GenerationSession` authorizes creation/read of many `Task` records.
- `WorkerAccount` may execute many `Task` records (via routing namespace/workspace).
- each `Task` may produce one `GalleryItem` projection (done-state view).
- `AdminSession` actions produce many `AdminAuditEvent` rows.
- `ModelConfigurationEntry` governs valid `Task.parameters` for each `Task.model` + `Task.mode`.

## State Transition Summary

### Task
- `pending` -> `processing` -> `done`
- `pending` -> `processing` -> `failed`
- stale `processing` -> `failed` by TTL policy

### WorkerAccount
- `pending` -> `ready` (successful health)
- `ready` -> `failed` (explicit health/runtime failure)
- `ready|pending|failed` -> `disabled` (admin action)
- `disabled` -> `ready|pending` (admin action + health)

### Sessions
- `active` -> `revoked`
- `active` -> `expired`
