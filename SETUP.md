# Gooni Gooni — Project Setup & Deployment Guide

## 📐 Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│  USER BROWSER                                                │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼─────────────────────────────────────┐
│  GCP VM (OpenClaw)   — Docker container                      │
│  nginx  :80/:443  → serves built React SPA (dist/)          │
│  nginx proxy /api/*  → Modal backend URL                     │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS (Modal URL)
┌────────────────────────▼─────────────────────────────────────┐
│  Modal Cloud (serverless)                                    │
│  FastAPI ASGI  app — gooni-gooni-backend                     │
│  ├── run_video_generation()  — A10G GPU                      │
│  └── run_image_generation()  — T4 GPU                        │
│  Volumes: model-cache, results (SQLite DB + files)           │
└──────────────────────────────────────────────────────────────┘
```

## ✅ Audit Results

### Frontend (React + Vite)
| Check | Status | Notes |
|---|---|---|
| React 18 + Vite 6 | ✅ | `package.json` configured |
| TailwindCSS 4 | ✅ | Via `@tailwindcss/vite` plugin |
| Package manager | ⚠️ `npm` | No lockfile committed — run `npm install` |
| TypeScript types | ⚠️ | `@types/react` missing as devDep — `npm i -D @types/react @types/react-dom` |
| `VITE_API_URL` env | ✅ | `.env.example` present |
| `VITE_ADMIN_KEY` env | ✅ | Added to `.env.example` |

### Backend (Python + Modal)
| Check | Status | Notes |
|---|---|---|
| FastAPI + Pydantic v2 | ✅ | `requirements.txt` |
| Modal SDK `>=0.64` | ✅ | |
| Auth (`X-API-Key`) | ✅ | `auth.py` — env `API_KEY` |
| Admin auth (`X-Admin-Key`) | ✅ | `app.py` — env `ADMIN_KEY` |
| SQLite storage | ✅ | `storage.py`, WAL mode |
| Account rotation | ✅ | `accounts.py`, `router.py` |
| Unit tests (89 passing) | ✅ | `pytest backend/tests/` |
| Phr00t model (safetensors) | ✅ | `from_single_file()` |
| AniSora V3.2 subfolder | ✅ | subfolder=`V3.2` |
| HF token for gated models | ⚠️ | Needed for FLUX.1-dev — set `HF_TOKEN` secret |

### Issues to Fix Before Production
| Issue | Fix |
|---|---|
| No `package-lock.json` / `pnpm-lock.yaml` | Run `npm install` to generate |
| No `@types/react` devDep | `npm i -D @types/react @types/react-dom` |
| `AdminPanel.tsx` not wired to `App.tsx` | Add `onAdminClick` state in `App.tsx` |
| `HF_TOKEN` Modal secret | Required for `black-forest-labs/FLUX.1-dev` (gated) |
| No `.gitignore` | Create (see below) |

---

## 🚀 Step-by-Step Setup

### 1. Prerequisites

| Tool | Version | Install |
|---|---|---|
| Node.js | ≥ 20 | `winget install OpenJS.NodeJS` |
| npm | ≥ 10 | Included with Node |
| Python | 3.11 | `winget install Python.Python.3.11` |
| Modal CLI | ≥ 0.64 | `pip install modal` |
| Docker Desktop | latest | [docker.com/get-started](https://www.docker.com/get-started/) |
| gcloud CLI | latest | [cloud.google.com/sdk](https://cloud.google.com/sdk/) |

---

### 2. Frontend Setup

```bash
# In project root
npm install
npm i -D @types/react @types/react-dom

# Copy env file
cp .env.example .env

# Edit .env
VITE_API_URL=https://YOUR_WORKSPACE--gooni-gooni-backend.modal.run
VITE_API_KEY=your-api-key
VITE_ADMIN_KEY=your-admin-key

# Test dev server
npm run dev
```

---

### 3. Backend Setup — Modal

```bash
# Authenticate
modal setup            # opens browser for OAuth

# Create required secrets
modal secret create gooni-api-key   API_KEY=your-strong-api-key
modal secret create gooni-admin     ADMIN_KEY=your-strong-admin-key
modal secret create huggingface     HF_TOKEN=hf_your_token_here

# Deploy backend (creates Modal Volumes automatically)
modal deploy backend/app.py

# The deploy output prints the URL — copy it to VITE_API_URL
# Example: https://myworkspace--gooni-gooni-backend.modal.run
```

#### First-run: Pre-cache models
```bash
# After deploy, trigger a dummy generation to warm model cache
# (models download on first generation — subsequent calls are fast)
curl -X POST https://YOUR_URL/generate \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"flux","type":"image","mode":"txt2img","prompt":"test"}'
```

---

### 4. Build Frontend for Production

```bash
# Set production env
cp .env.example .env.production
# Edit .env.production with real Modal URL

# Build
npm run build
# Output: dist/  (static files ready to serve)
```

---

### 5. Docker — Build & Push Frontend

```bash
# Build image
docker build -t gooni-gooni-frontend:latest .

# Test locally
docker run -p 8080:80 gooni-gooni-frontend:latest
# Open http://localhost:8080

# Push to DockerHub
docker login
docker tag gooni-gooni-frontend:latest YOUR_DOCKERHUB_USER/gooni-gooni:latest
docker push YOUR_DOCKERHUB_USER/gooni-gooni:latest
```

---

### 6. Deploy to GCP (OpenClaw VM)

```bash
# SSH into your OpenClaw VM
gcloud compute ssh openclaw --zone YOUR_ZONE

# On the VM — pull and run
docker pull YOUR_DOCKERHUB_USER/gooni-gooni:latest
docker run -d \
  --name gooni \
  --restart unless-stopped \
  -p 80:80 \
  -p 443:443 \
  YOUR_DOCKERHUB_USER/gooni-gooni:latest
```

---

## 🔐 Environment Variables Reference

| Variable | Where | Description |
|---|---|---|
| `API_KEY` | Modal Secret `gooni-api-key` | Auth key for all API endpoints |
| `ADMIN_KEY` | Modal Secret `gooni-admin` | Auth key for admin panel |
| `HF_TOKEN` | Modal Secret `huggingface` | HuggingFace token (FLUX gated model) |
| `VIDEO_GPU` | Modal env | Default: `A10G` |
| `IMAGE_GPU` | Modal env | Default: `T4` |
| `VITE_API_URL` | Frontend `.env` | Modal backend URL |
| `VITE_API_KEY` | Frontend `.env` | Same as `API_KEY` |
| `VITE_ADMIN_KEY` | Frontend `.env` | Same as `ADMIN_KEY` |

---

## 🐳 Docker Files Created

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage: build React → nginx |
| `docker-compose.yml` | Local dev orchestration |
| `nginx.conf` | SPA routing + API proxy |
| `.dockerignore` | Exclude node_modules etc. |

---

## 📁 Project Structure

```
gooni-gooni/
├── src/                  # React frontend
│   ├── app/              # Components, pages, contexts
│   └── styles/           # CSS
├── backend/              # Modal Python backend
│   ├── app.py            # Main Modal app (FastAPI + GPU functions)
│   ├── models/           # Pipeline implementations
│   ├── accounts.py       # Multi-account store
│   ├── router.py         # Account rotation
│   └── deployer.py       # Per-account deploy helper
├── Dockerfile            # Frontend container
├── docker-compose.yml    # Local orchestration
├── nginx.conf            # Nginx config for SPA + proxy
└── .env.example          # Environment template
```

---

## 📋 Readiness Checklist

- [ ] `npm install` run → `node_modules/` present
- [ ] `.env` created from `.env.example`
- [ ] `modal setup` done (authenticated)
- [ ] Modal Secrets created: `gooni-api-key`, `gooni-admin`, `huggingface`
- [ ] `modal deploy backend/app.py` — URL obtained
- [ ] `VITE_API_URL` in `.env` updated with Modal URL
- [ ] `npm run build` succeeds → `dist/` created
- [ ] Docker image built and pushed to DockerHub
- [ ] GCP VM running and Docker installed
- [ ] Container deployed on GCP
