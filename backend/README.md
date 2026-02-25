# Gooni Gooni — Backend

Modal-based FastAPI backend for AI content generation (images & video).

## Architecture

```
backend/
├── app.py              ← Main Modal app + FastAPI ASGI server
├── config.py           ← Volumes, model IDs, GPU config
├── schemas.py          ← Pydantic request/response models
├── auth.py             ← X-API-Key middleware
├── storage.py          ← SQLite gallery + volume helpers
├── requirements.txt
├── models/
│   ├── base.py         ← Abstract pipeline base class
│   ├── anisora.py      ← Index-AniSora V3.2 (anime video, A10G)
│   ├── phr00t.py       ← Phr00t WAN 2.2 Rapid (realistic video, A10G)
│   ├── pony.py         ← Pony Diffusion V6 XL (anime image, T4)
│   └── flux.py         ← Flux.1 [dev] NF4 (realistic image, T4)
└── tests/
    └── test_api.py     ← HTTP smoke tests
```

## Prerequisites

1. **Modal account** — [modal.com](https://modal.com)
2. **Modal CLI installed** locally:
   ```bash
   pip install modal
   modal setup        # authenticate
   ```
3. **HuggingFace token** (for gated models):
   ```bash
   modal secret create huggingface HF_TOKEN=hf_xxx
   ```

## Setup

### 1. Create Modal Secret (API key)

```bash
modal secret create gooni-api-key API_KEY=YOUR_SECRET_KEY
```

### 2. (Optional) Override model IDs

Add to the same secret or create new ones:

```bash
modal secret create gooni-models \
  ANISORA_MODEL_ID="BiliBili/Index-AniSora" \
  PHR00T_MODEL_ID="Wan-AI/Wan2.2-Remix" \
  PONY_MODEL_ID="John6666/pony-realism-v22main-sdxl" \
  FLUX_MODEL_ID="black-forest-labs/FLUX.1-dev"
```

### 3. Deploy

```bash
# From the project root
modal deploy backend/app.py
```

After deploy, Modal prints:
```
✓ Created web endpoint https://YOUR_WORKSPACE--gooni-api.modal.run
```

### 4. Configure frontend

Copy `.env.example` → `.env` and fill in the values:

```bash
cp .env.example .env
# Edit .env:
# VITE_API_URL=https://YOUR_WORKSPACE--gooni-api.modal.run
# VITE_API_KEY=YOUR_SECRET_KEY
```

Then restart the dev server:
```bash
npm run dev
```

## API Reference

Auto-generated Swagger docs available at:
```
GET https://YOUR_WORKSPACE--gooni-api.modal.run/docs
```

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | ✗ | Health check |
| `GET` | `/models` | ✓ | List models + schemas |
| `POST` | `/generate` | ✓ | Start generation → `{task_id}` |
| `GET` | `/status/{id}` | ✓ | Poll task status + progress |
| `GET` | `/results/{id}` | ✓ | Download result (video/image) |
| `GET` | `/preview/{id}` | ✓ | Thumbnail JPEG |
| `GET` | `/gallery` | ✓ | List gallery (paginated) |
| `DELETE` | `/gallery/{id}` | ✓ | Delete item |

All protected endpoints require header: `X-API-Key: YOUR_SECRET_KEY`

## Running Tests

```bash
pip install httpx pytest

# Against your deployed backend
pytest backend/tests/test_api.py -v \
  --base-url https://YOUR_WORKSPACE--gooni-api.modal.run \
  --api-key YOUR_SECRET_KEY

# Or via env vars
export BACKEND_URL=https://...
export API_KEY=...
pytest backend/tests/test_api.py -v
```

## Storage

| Volume | Name | Path | Contents |
|--------|------|------|---------|
| Models | `model-cache` | `/model-cache` | HuggingFace weights |
| Results | `results` | `/results` | `gallery.db` + `{task_id}/result.*` + `{task_id}/preview.jpg` |

## Cost Estimates (Modal)

| Model | GPU | Typical time | ~Cost |
|-------|-----|-------------|-------|
| anisora (81 frames) | A10G | ~4–8 min | $0.04–0.08 |
| phr00t (81 frames) | A10G | ~1–2 min | $0.01–0.02 |
| pony (1024px) | T4 | ~30–60 sec | $0.003–0.006 |
| flux (1024px) | T4 | ~20–40 sec | $0.002–0.004 |
