# Backend

Modal + FastAPI backend для единственного pipeline Pony Diffusion V6 XL.

Основные файлы:

- `app.py` — Modal class, очередь FunctionCall и HTTP API;
- `pony_contract.json` — общий frontend/backend контракт;
- `schemas.py` — строгая Pydantic-валидация;
- `models/pony.py` — persistent txt2img/img2img pipeline;
- `storage.py` — отдельная директория и manifest для каждого результата;
- `tests/` — schema, storage, auth, contract и live GPU проверки.

Задачи не хранятся в SQLite. Их состояние берётся из `modal.FunctionCall`, поэтому исключение или timeout не может остаться вечным `pending`.

Деплой:

```bash
modal secret create gooni-api-key API_KEY="replace-me"
modal deploy backend/app.py
```

См. корневой [SETUP.md](../SETUP.md).
