# Установка и деплой

## 1. Modal backend

Установите и авторизуйте Modal:

```bash
python -m pip install "modal>=1.1.4,<2"
modal setup
```

Создайте ключ API:

```bash
modal secret create gooni-api-key API_KEY="replace-with-a-long-random-key"
```

Разверните backend из корня репозитория:

```bash
modal deploy backend/app.py
```

После деплоя Modal покажет URL вида:

```text
https://YOUR-WORKSPACE--gooni-api.modal.run
```

Модель публичная, поэтому Hugging Face token не обязателен. Первый cold start скачивает модель в persistent Volume `model-cache`; следующие генерации повторно используют модель внутри живого GPU-контейнера.

Опциональные переменные:

| Переменная | По умолчанию | Назначение |
|---|---:|---|
| `PONY_MODEL_ID` | `Polenov2024/Pony-Diffusion-V6-XL` | Другой совместимый SDXL pipeline |
| `IMAGE_GPU` | `T4` | Тип Modal GPU |
| `IMAGE_TIMEOUT` | `600` | Timeout одного inference |
| `IMAGE_STARTUP_TIMEOUT` | `900` | Timeout загрузки модели |
| `IMAGE_MAX_CONTAINERS` | `1` | Параллельные GPU-контейнеры |
| `CORS_ORIGINS` | `*` | Список frontend origins через запятую |

## 2. Frontend

Создайте `.env`:

```bash
cp .env.example .env
```

Укажите только публичный адрес backend:

```dotenv
VITE_API_URL=https://YOUR-WORKSPACE--gooni-api.modal.run
```

API key не встраивается в JavaScript bundle. Откройте **Settings** в приложении, вставьте URL и ключ, затем нажмите **Test connection**.

Локальная разработка:

```bash
npm ci
npm run dev
```

Production build:

```bash
npm run build
```

Docker:

```bash
docker compose up --build
```

Откройте `http://localhost:8080`.

## 3. Проверка

```bash
python -m compileall -q backend
python backend/tests/run_contract_checks.py
npm run build
```

После установки test-зависимостей:

```bash
python -m pip install pytest httpx fastapi
pytest backend/tests -m "not live_gpu"
```

Реальный GPU smoke test:

```bash
pytest backend/tests/test_api.py -m live_gpu \
  --base-url https://YOUR-WORKSPACE--gooni-api.modal.run \
  --api-key YOUR_KEY
```

## Поведение состояний

- `/generate` возвращает Modal FunctionCall ID.
- Пока call исполняется, `/status` возвращает `processing`.
- Любое исключение model startup или inference возвращается как `failed`.
- Успешный call возвращает manifest и ссылки на результат.
- Кнопка Cancel вызывает `FunctionCall.cancel()`.
- UI переживает перезагрузку страницы, повторяет временно упавший polling пять раз и не стирает backend-ошибку.
