# Data Model: Стабильная авторизация и статусы админ-панели

## 1) GenerationSession

Назначение: авторизация пользовательских вызовов генерации без передачи постоянного `API_KEY` в клиент.

### Fields

- `session_id` (UUID, primary identifier)
- `issued_at` (datetime, UTC)
- `expires_at` (datetime, UTC = `issued_at + 24h`)
- `status` (enum: `active`, `expired`, `revoked`)
- `client_context` (optional string/hash для минимальной телеметрии)

### Validation Rules

- TTL фиксированный: 24 часа.
- Автопродление запрещено.
- Любая операция генерации после `expires_at` возвращает auth error.

### State Transitions

- `active -> expired` (по времени)
- `active -> revoked` (явный logout/revoke/security event)
- `expired` и `revoked` являются терминальными.

## 2) AdminSession

Назначение: доступ в admin-панель без повторного ввода ключа в рамках безопасного idle-window.

### Fields

- `session_id` (UUID)
- `issued_at` (datetime, UTC)
- `last_activity_at` (datetime, UTC)
- `idle_timeout_seconds` (constant = 43200)
- `status` (enum: `active`, `expired`, `revoked`)

### Validation Rules

- Сессия активна только если `now - last_activity_at <= 12h`.
- При превышении 12 часов неактивности сессия истекает.
- Обновление `last_activity_at` допускается только на успешных admin-запросах.

### State Transitions

- `active -> expired` (idle timeout)
- `active -> revoked` (logout/forced revoke)

## 3) ModalAccount

Назначение: описывает воркер-аккаунт для multi-account dispatch.

### Fields

- `id` (UUID, primary key)
- `label` (string, user-defined name)
- `workspace` (nullable string)
- `status` (enum: `pending`, `checking`, `ready`, `failed`, `disabled`)
- `last_error` (nullable string)
- `use_count` (int)
- `last_used` (nullable datetime)
- `added_at` (datetime)

### Validation Rules

- `ready` допустим только после успешного health-check.
- `failed` выставляется при неуспешном health-check/deploy.
- Клиентский UI не может задавать итоговые статусы; отображает серверные значения.

### State Transitions

- `pending -> checking` (start deploy/verification)
- `checking -> ready` (deploy+health-check success)
- `checking -> failed` (deploy/health-check failure)
- `failed -> checking` (manual retry/redeploy)
- `ready -> checking` (manual redeploy/recheck)
- `* -> disabled` (admin disable)
- `disabled -> ready` или `disabled -> checking` (admin enable/deploy policy)

### Forbidden Transitions

- `ready -> pending` без явного события “new credentials/new account”.
- `failed -> ready` без фазы `checking`.

## 4) GenerationTask (existing)

Назначение: трекинг инференса и выдача результата пользователю.

### Relevant Fields

- `id`, `status`, `progress`, `model`, `type`, `mode`
- `result_path`, `preview_path`, `error_msg`
- `created_at`, `updated_at`

### Status Constraints

- Терминальные состояния: `done`, `failed`.
- Для застрявших задач действует stale cleanup policy.

## Relationships

- `GenerationSession` 1:N `GenerationTask` (одна сессия может запускать несколько задач).
- `AdminSession` 1:N admin actions (audit/log correlation).
- `ModalAccount` 1:N dispatch attempts / health events.

## Derived Operational Entities

### AccountHealthEvent (logical)

- `account_id`, `previous_status`, `new_status`, `reason`, `timestamp`
- Используется для observability и расследования инцидентов.
