# RUNBOOK - Gooni Gooni (VM + Modal)

Last updated: 2026-02-27
Owner: Codekeeper45

## 1. Environment map

### Production VM (frontend container)
- Host name: `openclaw-server`
- Zone: `us-east1-b`
- External IP: `34.73.173.191`
- Runtime: Docker container `gooni-gooni`
- App URL: `http://34.73.173.191/`
- Admin URL: `http://34.73.173.191/admin`
- Health URL: `http://34.73.173.191/health`

### Modal (backend API)
- Workspace: `yapparov-emir-f`
- App: `gooni-gooni-backend`
- API URL: `https://yapparov-emir-f--gooni-api.modal.run`
- Direct admin URL (fallback mode): `https://yapparov-emir-f--gooni-api.modal.run/admin`
- Health URL: `https://yapparov-emir-f--gooni-api.modal.run/health`
- Docs URL: `https://yapparov-emir-f--gooni-api.modal.run/docs`
- Modal dashboard: `https://modal.com/apps/yapparov-emir-f/main/deployed/gooni-gooni-backend`

### GitHub
- Repo: `https://github.com/Codekeeper45/GooniGooni.git`
- Main work branch now: `001-fix-vram-oom`

## 2. Access prerequisites

### GCP access (VM)
```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud compute instances list
```

### Modal access
```bash
pip install modal
modal setup
modal profile current
```

### GitHub access
```bash
git remote -v
git ls-remote origin
```

## 2.1 SSH commands (VM)

### Connect to VM shell
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b
```

### Run one command on VM
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "hostname"
```

### Check app repo and current commit on VM
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "cd ~/gooni-gooni && git branch --show-current && git rev-parse --short HEAD"
```

### Update branch on VM
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "cd ~/gooni-gooni && git fetch --all --prune && git checkout 001-fix-vram-oom && git pull --ff-only origin 001-fix-vram-oom"
```

### Rebuild frontend container on VM (with fresh base images)
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "cd ~/gooni-gooni && sudo docker build --pull -t gooni-gooni:local --build-arg VITE_API_URL=https://yapparov-emir-f--gooni-api.modal.run ."
```

### Restart frontend container on VM
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo docker stop gooni-gooni >/dev/null 2>&1 || true; sudo docker rm gooni-gooni >/dev/null 2>&1 || true; sudo docker run -d --name gooni-gooni --restart unless-stopped -p 80:80 gooni-gooni:local"
```

### Check container status and logs
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo docker ps --filter name=gooni-gooni"
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo docker logs --tail=200 gooni-gooni"
```

### End-to-end VM deploy (single command)
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "bash -lc 'set -e; cd ~/gooni-gooni; git fetch --all --prune; git checkout 001-fix-vram-oom; git pull --ff-only origin 001-fix-vram-oom; sudo docker build --pull -t gooni-gooni:local --build-arg VITE_API_URL=https://yapparov-emir-f--gooni-api.modal.run .; sudo docker stop gooni-gooni >/dev/null 2>&1 || true; sudo docker rm gooni-gooni >/dev/null 2>&1 || true; sudo docker run -d --name gooni-gooni --restart unless-stopped -p 80:80 gooni-gooni:local; sleep 5; sudo docker ps --filter name=gooni-gooni --format \"table {{.Names}}\\t{{.Image}}\\t{{.Status}}\"'"
```

## 3. Secrets inventory (where they live)

Do not store real secret values in this repository.
All sensitive values must live in secret managers only.

| Secret name | Variables inside | Used by | Storage |
|---|---|---|---|
| `gooni-api-key` | `API_KEY` | backend API auth | Modal Secret |
| `gooni-admin` | `ADMIN_LOGIN`, `ADMIN_PASSWORD_HASH` | admin login/password auth | Modal Secret |
| `huggingface` | `HF_TOKEN` | model download | Modal Secret |
| `gooni-accounts` | `ACCOUNTS_ENCRYPT_KEY` (and account bootstrap values if used) | account crypto/deploy | Modal Secret |

### Required local env for frontend build/runtime
- `VITE_API_URL` (points to Modal API URL)

### Secret checks (without printing values)
```bash
modal secret list
```

### Current admin auth flow
- Admin UI does not ask for backend URL.
- Admin API is called via same-origin `/api` on VM.
- If UI is opened directly on `*.modal.run`, frontend falls back to direct `/admin/*` endpoints.
- Admin session uses secure httpOnly cookie `gg_admin_session`.

## 4. Secret creation/rotation

### Create password hash for admin (PBKDF2-SHA256)
```bash
python -c "import os,hashlib,binascii; pwd='CHANGE_ME'; it=600000; salt=binascii.hexlify(os.urandom(16)).decode(); digest=hashlib.pbkdf2_hmac('sha256', pwd.encode(), salt.encode(), it).hex(); print(f'pbkdf2_sha256${it}${salt}${digest}')"
```

### Create or update Modal secrets
```bash
modal secret create gooni-api-key API_KEY=<NEW_VALUE>
modal secret create gooni-admin ADMIN_LOGIN=<LOGIN> ADMIN_PASSWORD_HASH=<PBKDF2_HASH>
modal secret create huggingface HF_TOKEN=<NEW_VALUE>
modal secret create gooni-accounts ACCOUNTS_ENCRYPT_KEY=<NEW_VALUE>
```

### Rotation policy
- Rotate `API_KEY` and admin password hash on schedule and after any incident.
- Rotate `HF_TOKEN` if compromised.
- Rotate `ACCOUNTS_ENCRYPT_KEY` only with a migration plan (it protects encrypted account secrets).

## 5. Deploy procedures

### A) Deploy backend to Modal
From repo root:
```bash
modal deploy backend/app.py
```

Verify:
```bash
curl -sS https://yapparov-emir-f--gooni-api.modal.run/health
# expected: {"ok":true}
```

### B) Deploy frontend container to VM
From local machine:
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "bash -lc 'set -e; cd ~/gooni-gooni; git fetch --all --prune; git checkout 001-fix-vram-oom; git pull --ff-only origin 001-fix-vram-oom; sudo docker build --pull -t gooni-gooni:local --build-arg VITE_API_URL=https://yapparov-emir-f--gooni-api.modal.run .; sudo docker stop gooni-gooni >/dev/null 2>&1 || true; sudo docker rm gooni-gooni >/dev/null 2>&1 || true; sudo docker run -d --name gooni-gooni --restart unless-stopped -p 80:80 gooni-gooni:local; sleep 8; sudo docker ps --filter name=gooni-gooni --format \"table {{.Names}}\\t{{.Image}}\\t{{.Status}}\"'"
```

Verify:
```bash
curl -i http://34.73.173.191/health
# expected: HTTP 200 and body: OK
```

## 5.1 Modal commands used in operations

### Authentication and profile
```bash
modal setup
modal profile current
```

### Deploy backend
```bash
modal deploy backend/app.py
```

### Deploy backend with explicit GPU classes
```bash
VIDEO_GPU=A10G IMAGE_GPU=A10G modal deploy backend/app.py
```

### Check logs
```bash
modal app logs gooni-gooni-backend
modal app logs gooni-gooni-backend -f
```

### Check web endpoints
```bash
curl -sS https://yapparov-emir-f--gooni-api.modal.run/health
curl -sS https://yapparov-emir-f--gooni-api-health.modal.run
```

### Secret operations
```bash
modal secret list
modal secret create gooni-api-key API_KEY=<NEW_VALUE>
modal secret create gooni-admin ADMIN_LOGIN=<LOGIN> ADMIN_PASSWORD_HASH=<PBKDF2_HASH>
modal secret create huggingface HF_TOKEN=<NEW_VALUE>
modal secret create gooni-accounts ACCOUNTS_ENCRYPT_KEY=<NEW_VALUE>
```

### Optional: local route testing
```bash
modal serve backend/app.py
```

## 6. Operational checks

### Backend checks
```bash
curl -sS https://yapparov-emir-f--gooni-api.modal.run/health
curl -sS https://yapparov-emir-f--gooni-api.modal.run/models -H "X-API-Key: <API_KEY>"
```

### VM checks
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo docker ps --filter name=gooni-gooni"
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo docker logs --tail=100 gooni-gooni"
```

### Modal logs
```bash
modal app logs gooni-gooni-backend
```

## 7. Rollback

### Backend rollback (Modal)
```bash
git checkout <PREVIOUS_GOOD_COMMIT>
modal deploy backend/app.py
```

### VM rollback
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "bash -lc 'cd ~/gooni-gooni; git fetch --all --prune; git checkout <PREVIOUS_GOOD_BRANCH_OR_COMMIT>; sudo docker build --pull -t gooni-gooni:local --build-arg VITE_API_URL=https://yapparov-emir-f--gooni-api.modal.run .; sudo docker stop gooni-gooni >/dev/null 2>&1 || true; sudo docker rm gooni-gooni >/dev/null 2>&1 || true; sudo docker run -d --name gooni-gooni --restart unless-stopped -p 80:80 gooni-gooni:local'"
```

## 8. Troubleshooting quick list

- `401/403` on API: check `API_KEY`, session cookie, CORS origins.
- Admin auth fails: check `gooni-admin` secret has valid `ADMIN_LOGIN` + `ADMIN_PASSWORD_HASH`.
- `Failed to fetch` on admin login: open admin via `http://34.73.173.191/admin` (VM) or verify `/api` proxy in `nginx.conf`.
- Model load errors: check `huggingface` secret and model access rights.
- Worker account failures: check `gooni-accounts` secret and admin account statuses.
- Frontend cannot call backend: rebuild VM image with correct `VITE_API_URL`.

## 9. Security rules (mandatory)

- Never commit real passwords, keys, tokens, or `.env` with real values.
- Never print full keys in logs.
- Keep secrets only in Modal Secret Manager and private operator vault.
- If compromise suspected: rotate secrets first, then redeploy backend and VM.
