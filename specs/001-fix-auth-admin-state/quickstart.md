# Quickstart: Стабильная авторизация и статусы админ-панели

## Цель

Проверить, что:
1. генерация работает без ручного `X-API-Key` в UI;
2. admin-сессия сохраняется между заходами и истекает после 12 часов неактивности;
3. статусы аккаунтов server-authoritative и корректно переходят в `ready/failed`.

## Prerequisites

- Backend развернут: `modal deploy backend/app.py`
- Frontend запущен с корректным `VITE_API_URL`
- Modal secrets доступны: `gooni-api-key`, `gooni-admin`, `gooni-accounts`

## 1) Smoke: generation auth without manual key

1. Открыть приложение в чистом браузерном профиле.
2. Убедиться, что `localStorage.mg_api_key` отсутствует.
3. Выполнить запуск генерации с валидным prompt.
4. Проверить, что:
   - задача создаётся (`202`),
   - в UI нет ошибки `Invalid or missing X-API-Key`,
   - `status/result/preview` доступны в рамках session policy.

## 2) Smoke: admin session persistence

1. Выполнить вход в Admin.
2. Перейти в дашборд, затем обновить страницу и снова открыть `/admin`.
3. Проверить, что повторный ручной ввод ключа не требуется (в рамках active session).
4. Эмулировать idle > 12h (или тестовым конфигом сократить TTL).
5. Проверить принудительный re-auth после истечения idle timeout.

## 3) Smoke: account statuses and health transitions

1. Добавить/выбрать аккаунт для deploy.
2. Наблюдать переходы:
   - `pending -> checking`
   - `checking -> ready` (при успехе) или `checking -> failed` (при ошибке)
3. Повторно открыть админку.
4. Проверить, что статус сохраняется и не откатывается в `pending` без явного redeploy.

## 4) Required verification commands

```bash
pytest backend/tests/
npm run build
pytest backend/tests/test_api.py -v --base-url <url> --api-key <key>
```

## 5) Regression checklist

- Нет массовых 403 на `/generate` в типовом пользовательском сценарии.
- Серверный постоянный секрет не отображается в UI.
- Failed health-check не приводит к `ready` без успешной повторной проверки.
- UI не переопределяет статус аккаунта локально.

## 6) Run Log (2026-02-26)

Выполненные проверки:

- `pytest backend/tests/test_api.py --collect-only -q`
  - Результат: `11 tests collected` (контракты и сценарии собираются корректно).
- `python -c "... ast.parse(...)"` для изменённых backend-файлов
  - Результат: `OK` (синтаксис Python валиден).

Проблемы среды при полном прогоне:

- `pytest backend/tests/` и таргет-прогоны в этой среде периодически зависают/блокируются.
- `npm run build` в текущей среде падает с `spawn EPERM` на этапе `esbuild`.

Следующий шаг для полного закрытия проверки:

1. Прогнать `pytest backend/tests/` на чистом CI/VM runner.
2. Прогнать `npm run build` на runner без локальных ограничений `EPERM`.
3. Прогнать live smoke:
   `pytest backend/tests/test_api.py -v --base-url <url> --api-key <key> --admin-key <admin_key> --request-timeout 15`.
