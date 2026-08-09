# Gooni Gooni

Надёжный веб-интерфейс для генерации изображений через Pony Diffusion V6 XL на Modal.

Проект намеренно поддерживает только один проверяемый вертикальный поток:

- `txt2img` и `img2img`;
- prompt и negative prompt;
- разрешение, steps, CFG, sampler, clip skip, seed и формат;
- denoising strength и reference image для `img2img`;
- восстановление активной задачи после перезагрузки;
- отмена, настоящие backend-ошибки и повтор после сбоя;
- постоянная gallery с просмотром, скачиванием и удалением.

## Архитектура

```text
React UI
  └─ strict JSON payload
      └─ FastAPI on Modal
          └─ Modal FunctionCall (queue, result, error, cancel)
              └─ persistent PonyGenerator container
                  └─ result + preview + manifest on Modal Volume
```

`backend/pony_contract.json` — общий источник defaults, limits, sampler'ов и разрешений для frontend и backend. Backend отклоняет неизвестные поля, поэтому неподдержанная UI-функция не может пройти незаметно.

SQLite и фиктивные проценты прогресса не используются. Modal `FunctionCall` является источником состояния и возвращает ошибки загрузки модели, inference и timeout.

## Быстрый запуск

Полная инструкция находится в [SETUP.md](SETUP.md).

```bash
npm ci
npm run dev
```

Проверки:

```bash
npm run build
python backend/tests/run_contract_checks.py
pytest backend/tests -m "not live_gpu"
```

## API

| Метод | Endpoint | Назначение |
|---|---|---|
| `GET` | `/health` | Проверка API |
| `GET` | `/models` | Единственный поддерживаемый контракт Pony |
| `POST` | `/generate` | Запуск генерации |
| `GET` | `/status/{task_id}` | Результат или настоящая ошибка Modal |
| `DELETE` | `/tasks/{task_id}` | Отмена |
| `GET` | `/gallery` | Сохранённые изображения |
| `GET` | `/results/{id}` | Полный файл |
| `GET` | `/preview/{id}` | Preview |
| `DELETE` | `/gallery/{id}` | Удаление результата |

Все endpoints, кроме `/health`, используют заголовок `X-API-Key`. Ключ никогда не передаётся в query string.
