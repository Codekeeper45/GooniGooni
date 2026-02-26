# Phase 0 Research: Стабильная авторизация и статусы админ-панели

## Scope

Фокус: устранение `403` в генерации, безопасная безручная авторизация клиента,
стабильные серверные статусы Modal-аккаунтов, устойчивый админ-вход без хранения
постоянных секретов в браузере.

## Findings and Decisions

### 1) User Generation Auth Model

- **Decision**: Ввести server-managed generation session (TTL 24 часа, без auto-refresh),
  постоянный `API_KEY` оставить только для server-to-server вызовов.
- **Rationale**: Текущий frontend использует `localStorage.mg_api_key`; при пустом значении
  запросы `/generate` и `/status` уходят без `X-API-Key` и получают `403`.
  Сессионная модель устраняет ручной ввод и сокращает риск утечки постоянного секрета.
- **Alternatives considered**:
  - Продолжать хранить `mg_api_key` в `localStorage` — отвергнуто (утечка через клиент/инструменты браузера).
  - Хардкодить «зашифрованный» ключ во frontend bundle — отвергнуто (ключ извлекаем, не является безопасным).

### 2) Token Transport for Browser Media Access

- **Decision**: Передавать generation session через `HttpOnly + Secure + SameSite=Strict` cookie.
- **Rationale**: `<img>/<video>` не отправляют custom headers; cookie-механизм покрывает
  `/results/{task_id}` и `/preview/{task_id}` без query-key workaround.
- **Alternatives considered**:
  - Query param `api_key` — отвергнуто как менее безопасный (логирование URL, history, referer).
  - Bearer token только в JS header — отвергнуто для media `src` запросов.

### 3) Admin Session Persistence Policy

- **Decision**: Сохранять admin-сессию между заходами, завершать после 12 часов неактивности.
- **Rationale**: `sessionStorage` очищается при закрытии вкладки и визуально создаёт потерю ключа.
  Политика idle-timeout 12h снижает операционное трение без бессрочного доступа.
- **Alternatives considered**:
  - Session only per-tab — отвергнуто (плохой UX для оператора).
  - 30 дней / бессрочно — отвергнуто (избыточный риск при компрометации браузера).

### 4) Account Status Source of Truth and FSM

- **Decision**: Сервер — единственный источник истины для статусов аккаунтов;
  вводится явная FSM `pending -> checking -> ready|failed` (+ retry `failed -> checking`,
  redeploy `ready -> checking`).
- **Rationale**: Текущие `pending` reset приходят в основном из серверной логики deploy-cycle,
  а не из UI. Явный `checking` убирает неоднозначность и предотвращает ложные `ready -> pending`.
- **Alternatives considered**:
  - Локальный optimistic state в UI — отвергнуто (рассинхрон с реальным backend состоянием).
  - Держать только `pending/ready/failed` без `checking` — отвергнуто (нет прозрачности этапа проверки).

### 5) Failure Semantics for Health-Check

- **Decision**: При неуспешном health-check переводить аккаунт в `failed`; в `ready`
  возвращать только после следующего успешного health-check.
- **Rationale**: Исключает маршрутизацию запросов на неготовый воркер и стабилизирует
  поведение fallback-роутера.
- **Alternatives considered**:
  - Оставлять `ready` с warning — отвергнуто (ложно-позитивный operational сигнал).
  - Возвращать в `pending` — отвергнуто (теряется различие между “не проверен” и “провален”).

### 6) CORS and Compatibility Boundary

- **Decision**: Сохранить allowlist origins и обеспечить cookie-compatible CORS политику
  для frontend домена/VM.
- **Rationale**: В проекте уже есть explicit origins + regex fallback; новая session cookie модель
  требует корректных `allow_credentials` и origin alignment.
- **Alternatives considered**:
  - Открытый CORS на `*` — отвергнуто (нарушает security hygiene конституции).

## Phase 0 Output

- Все ранее потенциально неясные решения по auth/session/status lifecycle закрыты.
- Дополнительных неразрешённых вопросов для Phase 1 не осталось.
