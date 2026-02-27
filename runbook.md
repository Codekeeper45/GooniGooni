# RUNBOOK - Gooni Gooni Production Operations

Last updated: 2026-02-27
Owner: Codekeeper45

## 1. Production topology

### VM layer (user-facing app + admin auth)
- Host: `openclaw-server`
- Zone: `us-east1-b`
- External IP: `34.73.173.191`
- Container: `gooni-gooni`
- Runtime inside container:
  - `nginx` serves frontend (`/`, `/admin`)
  - local `uvicorn` serves admin API behind same-origin `/api/*`

### Modal layer (generation backend)
- Workspace: `yapparov-emir-f`
- App: `gooni-gooni-backend`
- API URL: `https://yapparov-emir-f--gooni-api.modal.run`
- Health URL: `https://yapparov-emir-f--gooni-api.modal.run/health`
- Dashboard: `https://modal.com/apps/yapparov-emir-f/main/deployed/gooni-gooni-backend`

### GitHub
- Repo: `https://github.com/Codekeeper45/GooniGooni.git`
- Working branch: `001-fix-vram-oom`

## 2. Canonical URLs

- Site: `http://34.73.173.191/`
- Admin page: `http://34.73.173.191/admin`
- VM health: `http://34.73.173.191/health`
- VM local admin API health: `http://34.73.173.191/api/health`
- Modal API health: `https://yapparov-emir-f--gooni-api.modal.run/health`

## 3. Access setup

### GCP / VM
```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud compute instances list
```

### Modal
```bash
pip install modal
modal setup
modal profile current
```

### Repo access
```bash
git remote -v
git ls-remote origin
```

## 4. Secret model

Do not store real values in git.

### Modal secrets
- `gooni-api-key`: `API_KEY`
- `gooni-admin`: `ADMIN_LOGIN`, `ADMIN_PASSWORD_HASH`
- `huggingface`: `HF_TOKEN`
- `gooni-accounts`: `ACCOUNTS_ENCRYPT_KEY`

### VM runtime secrets
- File on VM: `/opt/gooni/admin.env`
- Used by local admin API in container (`--env-file /opt/gooni/admin.env`)

Example content:
```dotenv
ADMIN_LOGIN=admin
ADMIN_PASSWORD_HASH=pbkdf2_sha256$<iterations>$<salt>$<hex_digest>
ACCOUNTS_ENCRYPT_KEY=<FERNET_KEY>
ADMIN_COOKIE_SECURE=0
ADMIN_COOKIE_SAMESITE=lax
```

## 5. Admin auth details

- Admin UI does not require backend URL input.
- Admin UI talks to same-origin `/api/*` on VM.
- Local admin API is independent from Modal billing limits.
- Cookie name: `gg_admin_session`
- Cookie flags are controlled by:
  - `ADMIN_COOKIE_SECURE` (`1` for HTTPS)
  - `ADMIN_COOKIE_SAMESITE` (`lax`, `strict`, `none`)

## 6. Password hash generation

Generate PBKDF2 hash:
```bash
python -c "import os,hashlib,binascii; p='CHANGE_ME'; i=600000; s=binascii.hexlify(os.urandom(16)).decode(); d=hashlib.pbkdf2_hmac('sha256', p.encode(), s.encode(), i).hex(); print(f'pbkdf2_sha256${i}${s}${d}')"
```

## 7. VM operations

### SSH quick commands
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b
gcloud compute ssh openclaw-server --zone=us-east1-b --command "hostname"
gcloud compute ssh openclaw-server --zone=us-east1-b --command "cd ~/gooni-gooni && git branch --show-current && git rev-parse --short HEAD"
```

### Ensure admin env exists on VM
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo mkdir -p /opt/gooni /opt/gooni/results && sudo test -f /opt/gooni/admin.env || echo 'Create /opt/gooni/admin.env first'"
```

Generate Fernet key for `ACCOUNTS_ENCRYPT_KEY`:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Full VM deploy (recommended)

This command always updates git, rebuilds with fresh base images, and restarts container.
It fails fast because of `set -e`.

```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "bash -lc 'set -e; cd ~/gooni-gooni; git fetch --all --prune; git checkout 001-fix-vram-oom; git pull --ff-only origin 001-fix-vram-oom; sudo docker build --pull -t gooni-gooni:local --build-arg VITE_API_URL=https://yapparov-emir-f--gooni-api.modal.run .; sudo mkdir -p /opt/gooni/results; sudo test -f /opt/gooni/admin.env; sudo docker stop gooni-gooni >/dev/null 2>&1 || true; sudo docker rm gooni-gooni >/dev/null 2>&1 || true; sudo docker run -d --name gooni-gooni --restart unless-stopped -p 80:80 -v /opt/gooni/results:/results --env-file /opt/gooni/admin.env gooni-gooni:local; sleep 8; sudo docker ps --filter name=gooni-gooni --format "table {{.Names}}\\t{{.Image}}\\t{{.Status}}"'"
```

### Verify VM deployment
```bash
curl -i http://34.73.173.191/health
curl -i http://34.73.173.191/api/health
```

### Check container logs
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo docker logs --tail=200 gooni-gooni"
```

## 8. Modal operations

### Deploy backend
```bash
modal deploy backend/app.py
```

### Deploy with explicit GPU class
```bash
VIDEO_GPU=A10G IMAGE_GPU=A10G modal deploy backend/app.py
```

### Logs
```bash
modal app logs gooni-gooni-backend
modal app logs gooni-gooni-backend -f
```

### Health checks
```bash
curl -sS https://yapparov-emir-f--gooni-api.modal.run/health
curl -sS https://yapparov-emir-f--gooni-api-health.modal.run
```

## 9. End-to-end verification checklist

### A) Site and admin
```bash
curl -i http://34.73.173.191/
curl -i http://34.73.173.191/admin
curl -i http://34.73.173.191/api/health
```

### B) Admin login/session
```bash
# Login should return 204 and set cookie
curl -i -X POST http://34.73.173.191/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{"login":"<ADMIN_LOGIN>","password":"<ADMIN_PASSWORD>"}'
```

### C) Modal generation API
```bash
curl -i https://yapparov-emir-f--gooni-api.modal.run/health
curl -i https://yapparov-emir-f--gooni-api.modal.run/models -H "X-API-Key: <API_KEY>"
```

## 10. Rollback

### VM rollback to previous commit/branch
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "bash -lc 'set -e; cd ~/gooni-gooni; git fetch --all --prune; git checkout <PREVIOUS_GOOD_REF>; sudo docker build --pull -t gooni-gooni:local --build-arg VITE_API_URL=https://yapparov-emir-f--gooni-api.modal.run .; sudo docker stop gooni-gooni >/dev/null 2>&1 || true; sudo docker rm gooni-gooni >/dev/null 2>&1 || true; sudo docker run -d --name gooni-gooni --restart unless-stopped -p 80:80 -v /opt/gooni/results:/results --env-file /opt/gooni/admin.env gooni-gooni:local'"
```

### Modal rollback
```bash
git checkout <PREVIOUS_GOOD_REF>
modal deploy backend/app.py
```

## 11. Common incidents

### Admin login shows `Failed to fetch`
- Check VM container is running:
  - `sudo docker ps --filter name=gooni-gooni`
- Check local admin API:
  - `curl -i http://34.73.173.191/api/health`
- Check nginx proxy section `location /api/` in `nginx.conf`.

### Admin login returns `401/403`
- Verify `/opt/gooni/admin.env` values.
- Ensure `ADMIN_LOGIN`, `ADMIN_PASSWORD_HASH`, and `ACCOUNTS_ENCRYPT_KEY` are set correctly.
- Restart container after env changes.

### Modal returns `429` with billing text
- Root cause: Modal workspace spend limit reached.
- Action: fix billing/quota in Modal dashboard.
- Note: admin login on VM still works because it is local now.

### No changes after deploy
- Ensure git pulled latest commit on VM.
- Ensure docker image rebuilt with `--pull`.
- Ensure old container was removed and new one started.
- Confirm current running image:
  - `sudo docker ps --filter name=gooni-gooni`
  - `sudo docker inspect gooni-gooni --format '{{.Image}}'`

## 12. Security rules

- Never commit real passwords, API keys, or token secrets.
- Never print full secrets in logs.
- Store Modal secrets only in Modal secret manager.
- Store VM admin env only in `/opt/gooni/admin.env` with restricted access.
- After suspected compromise: rotate secrets first, then redeploy VM and Modal.
