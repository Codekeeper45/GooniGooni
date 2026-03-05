# RUNBOOK - Gooni Gooni Production Operations

Last updated: 2026-03-01
Owner: Codekeeper45

This document is the operational source of truth for:
- local development
- VM deploys
- Modal worker-account provisioning
- production verification
- incident response

This file intentionally does not store real secrets. Keep secret values out of git.

## 1. Production topology

### 1.1 Current serving model
- User-facing site runs on GCP VM `openclaw-server`
- External IP: `34.73.173.191`
- Main container name: `gooni-gooni`
- Container image tag used on VM: `gooni-gooni:local`

### 1.2 Inside the VM container
- `nginx` serves the frontend at `/` and `/admin`
- local `uvicorn` runs `backend/admin_local.py` at `127.0.0.1:8001`
- `nginx` proxies `/api/*` to the local admin API
- local admin API is the production gateway for browser requests

### 1.3 Modal worker model
- There is no permanent "main" or "leader" Modal account in production routing
- Worker accounts are a rotating pool
- All accounts are treated as equal candidates when `status=ready`
- New worker accounts are added and deployed from the admin panel
- Normal production flow should use Admin `Deploy` or `Deploy all`, not a manual direct deploy to one specific workspace

### 1.4 Routing rules
- Browser production traffic on VM must use same-origin `/api/*`
- Browser should not directly call `https://<workspace>--gooni-api.modal.run/*` from VM-hosted frontend
- Remote generation tasks use opaque task ids of the form `workspace::task_id`
- VM proxies `/api/status`, `/api/results`, `/api/preview` to the correct Modal workspace using that prefix

## 2. Canonical URLs

- Site: `http://34.73.173.191/`
- Admin page: `http://34.73.173.191/admin`
- VM health: `http://34.73.173.191/health`
- VM gateway health: `http://34.73.173.191/api/health`

Notes:
- A Modal workspace URL is not canonical for browser usage in production
- Modal workspace URLs are backend targets used by the VM gateway and by admin deploy logic

## 3. Repository structure

### 3.1 Top level
```text
backend/              Modal backend, VM admin API, account rotation, storage
docker/               Container startup scripts
qa_smoke/             Smoke test artifacts/scripts
specs/                Feature specs
src/                  Frontend source
Dockerfile            VM image build
nginx.conf            Frontend + /api reverse proxy
deploy-to-gcp.sh      VM deployment helper
package.json          Frontend dependencies/scripts
runbook.md            This document
```

### 3.2 Backend layout
```text
backend/
  app.py              Modal app definition, GPU functions, worker execution
  api.py              Direct Modal API surface (legacy/direct mode)
  admin_local.py      Local VM API and production browser gateway
  admin_security.py   Admin auth, sessions, rate limiting
  accounts.py         Account store, encryption, spending, status transitions
  router.py           Account carousel / autorotation
  deployer.py         Deploy, redeploy, health-check, warmup for worker accounts
  storage.py          SQLite + file metadata + session/task persistence
  auth.py             API key auth / generation auth helpers
  config.py           Runtime env config and model/runtime constants
  schemas.py          Pydantic request/response models
  models/
    base.py           Shared pipeline base utilities
    anisora.py        Video pipeline
    phr00t.py         Video pipeline
    pony.py           SDXL image pipeline
    flux.py           Flux image pipeline
  tests/              Backend tests
```

### 3.3 Frontend layout
```text
src/
  main.tsx
  inference_settings.json
  app/
    App.tsx
    Root.tsx
    routes.tsx
    admin/
      AdminDashboard.tsx
      AdminLoginPage.tsx
      adminSession.ts
    context/
      GenerationContext.tsx
      GalleryContext.tsx
    components/
      ...
    pages/
      ...
    utils/
      configManager.ts
      sessionClient.ts
      ...
```

## 4. Dependency inventory

### 4.1 Frontend build/runtime
- React 18
- TypeScript
- Vite 6.3.5
- React Router 7.13.0
- MUI 7.3.x
- Radix UI components
- date-fns
- lucide-react
- recharts
- react-hook-form

Primary commands:
```bash
npm install
npm run build
npm run dev
```

### 4.2 VM local admin API dependencies
From `backend/admin_requirements.txt`:
- `fastapi>=0.111`
- `uvicorn[standard]>=0.30`
- `pydantic>=2.7`
- `cryptography>=42`
- `httpx>=0.27`
- `modal>=0.64`

### 4.3 Modal worker/backend dependencies
From `backend/requirements.txt`:
- FastAPI / Uvicorn / Pydantic
- Modal
- `torch==2.4.0`
- `torchvision==0.18.1`
- `torchaudio==2.3.1`
- `diffusers>=0.32.0`
- `transformers>=4.43.0`
- `accelerate>=0.32.0`
- `safetensors>=0.4`
- `bitsandbytes>=0.43.0`
- `Pillow>=10`
- `imageio[ffmpeg]>=2.34`
- `numpy>=1.26`
- `huggingface_hub>=0.23`

## 5. Runtime configuration and env keys

### 5.1 VM runtime env file
File:
```text
/opt/gooni/admin.env
```

This file is mounted into the VM container through:
```bash
--env-file /opt/gooni/admin.env
```

### 5.1.1 Required VM env keys
- `API_KEY`
- `ADMIN_LOGIN`
- `ADMIN_PASSWORD_HASH`
- `ACCOUNTS_ENCRYPT_KEY`
- `HF_TOKEN`

Without these, the VM gateway and account provisioning will break.

### 5.1.2 VM auth/session env keys
- `ADMIN_COOKIE_SECURE`
- `ADMIN_COOKIE_SAMESITE`
- `ADMIN_IDLE_TIMEOUT_SECONDS`
- `GENERATION_SESSION_TTL_SECONDS`
- `MODAL_TARGET_ENV`

### 5.1.3 VM deploy / worker management env keys
- `ACCOUNT_DEPLOY_TIMEOUT_SECONDS`
- `ACCOUNT_DEPLOY_MAX_RETRIES`
- `ACCOUNT_DEPLOY_RETRY_BACKOFF_SECONDS`
- `ACCOUNT_DEPLOY_RETRY_MAX_BACKOFF_SECONDS`
- `ACCOUNT_HEALTH_ATTEMPTS`
- `ACCOUNT_HEALTH_INTERVAL_SECONDS`
- `ACCOUNT_AUTO_WARMUP_MODE`
- `ACCOUNT_WARMUP_TOTAL_TIMEOUT_SECONDS`
- `ACCOUNT_WARMUP_POLL_INTERVAL_SECONDS`

### 5.1.4 VM autorotation / spending env keys
- `ACCOUNT_MAX_FALLBACKS`
- `ACCOUNT_FAILED_COOLDOWN_SECONDS`
- `ACCOUNT_MAX_FAIL_COUNT`
- `VIDEO_COST_USD_ESTIMATE`
- `IMAGE_COST_USD_ESTIMATE`

### 5.1.5 Warmup / lane control env keys used by gateway logic
- `ENABLE_LANE_WARMUP`
- `WARMUP_DEFAULT_MODELS`
- `WARMUP_TTL_SECONDS`
- `WARMUP_COOLDOWN_SECONDS`
- `WARMUP_RETRIES`
- `WARMUP_CONNECT_TIMEOUT_SECONDS`
- `WARMUP_TIMEOUT_SECONDS`

### 5.1.6 Example VM env file
```dotenv
API_KEY=<shared_api_key>
ADMIN_LOGIN=<admin_login>
ADMIN_PASSWORD_HASH=pbkdf2_sha256$<iterations>$<salt>$<hex_digest>
ACCOUNTS_ENCRYPT_KEY=<fernet_key>
HF_TOKEN=<huggingface_token>
MODAL_TARGET_ENV=main
ADMIN_COOKIE_SECURE=0
ADMIN_COOKIE_SAMESITE=lax
```

### 5.2 Modal worker app env keys

### 5.2.1 Required in worker environment
- `API_KEY`
- `HF_TOKEN`

### 5.2.2 Build / identity
- `WORKER_BUILD_ID`
- `CACHE_VOLUME`
- `RESULTS_VOLUME`

### 5.2.3 Model ids / artifacts
- `ANISORA_MODEL_ID`
- `ANISORA_SUBFOLDER`
- `PHR00T_MODEL_ID`
- `PHR00T_FILENAME`
- `PONY_MODEL_ID`
- `PONY_VAE_MODEL_ID`
- `FLUX_MODEL_ID`

### 5.2.4 GPU / performance
- `VIDEO_GPU`
- `IMAGE_GPU`
- `VIDEO_TIMEOUT`
- `IMAGE_TIMEOUT`
- `VIDEO_CPU`
- `IMAGE_CPU`
- `VIDEO_CONCURRENCY`
- `IMAGE_CONCURRENCY`
- `VIDEO_LANE_WARM_MIN_CONTAINERS`
- `VIDEO_LANE_WARM_MAX_CONTAINERS`
- `IMAGE_LANE_WARM_MIN_CONTAINERS`
- `IMAGE_LANE_WARM_MAX_CONTAINERS`
- `VIDEO_DEGRADED_MIN_CONTAINERS`
- `IMAGE_DEGRADED_MIN_CONTAINERS`
- `IMAGE_PONY_MIN_CONTAINERS`
- `IMAGE_PONY_MAX_CONTAINERS`
- `IMAGE_FLUX_MIN_CONTAINERS`
- `IMAGE_FLUX_MAX_CONTAINERS`
- `API_MIN_CONTAINERS`

### 5.2.5 Queue / warmup / health
- `VIDEO_DEGRADED_QUEUE_MAX_DEPTH`
- `VIDEO_DEGRADED_QUEUE_MAX_WAIT_SECONDS`
- `VIDEO_LANE_HEALTH_GRACE_SECONDS`
- `VIDEO_LANE_ASSIGNMENT_TIMEOUT_SECONDS`
- `ENABLE_LANE_WARMUP`
- `WARMUP_RETRIES`
- `WARMUP_TIMEOUT_SECONDS`
- `WARMUP_DEFAULT_MODELS`
- `WARMUP_TTL_SECONDS`
- `WARMUP_COOLDOWN_SECONDS`

### 5.2.6 API / browser-facing behavior in direct Modal mode
- `PUBLIC_BASE_URL`
- `FRONTEND_ORIGINS`
- `ENABLE_DOCS`
- `GENERATION_SESSION_TTL_SECONDS`
- `ADMIN_SESSION_IDLE_TIMEOUT_SECONDS`
- `PENDING_WORKER_START_WARNING_SECONDS`
- `PENDING_WORKER_START_FAIL_SECONDS`
- `STALE_TASK_HOURS`
- `ARTIFACT_TTL_DAYS`
- `GEN_SESSION_MAX_ACTIVE_TASKS`
- `NO_READY_ACCOUNT_WAIT_SECONDS`

### 5.2.7 CUDA / PyTorch runtime
- `PYTORCH_CUDA_ALLOC_CONF`
- `CUDA_VISIBLE_DEVICES`
- `TORCH_CUDA_ARCH_LIST`

### 5.3 Test-only env keys
Used by backend integration tests:
- `BACKEND_URL`
- `API_KEY`
- `ADMIN_LOGIN`
- `ADMIN_PASSWORD_HASH`
- `TEST_REQUEST_TIMEOUT`
- `TEST_POLL_INTERVAL_SECONDS`
- `TEST_VIDEO_FLOW_TIMEOUT_SECONDS`
- `TEST_IMAGE_FLOW_TIMEOUT_SECONDS`
- `TEST_QUEUE_OVERLOAD_STORM_REQUESTS`
- `TEST_QUEUE_OVERLOAD_SUBMIT_INTERVAL_SECONDS`
- `TEST_ADMIN_IDLE_PROBE_SECONDS`
- `TEST_FRONTEND_ORIGIN`
- `TEST_FORCE_WORKER_TIMEOUT`

## 6. Security rules

- Never commit real passwords, tokens, API keys, or secret hashes
- Never write full secrets into `runbook.md`
- Store VM runtime secrets only in `/opt/gooni/admin.env`
- Store Modal secrets only in Modal secret manager
- Do not log full token values
- Rotate secrets first if compromise is suspected, then redeploy

## 7. Admin login and session model

- Admin UI does not require entering a backend URL
- Admin UI talks to same-origin `/api/*` only
- Admin cookie name: `gg_admin_session`
- Generation cookie name: `gg_session`
- Browser generation session is required before `/api/generate`, `/api/status`, `/api/results`, `/api/preview`

Password handling:
- `ADMIN_PASSWORD_HASH` is PBKDF2-SHA256
- Generate all required shared env values automatically:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap-shared-env.ps1 -OutputPath .env.generated
```

```bash
bash scripts/bootstrap-shared-env.sh .env.generated
```

- The generated file includes:
  - `API_KEY`
  - `ADMIN_LOGIN`
  - `ADMIN_PASSWORD_HASH`
  - `ACCOUNTS_ENCRYPT_KEY`
  - `HF_TOKEN` placeholder (fill manually)

## 8. Local development commands

### 8.1 Frontend
```bash
npm install
npm run dev
npm run build
```

### 8.2 Backend tests
```bash
pytest backend/tests/test_admin_security.py -q
pytest backend/tests/test_pony_pipeline.py -q
```

### 8.3 Useful local git commands
```bash
git status --short
git diff -- src/app/context/GenerationContext.tsx
git add <path>
git commit -m "<message>"
git push origin 001-pipeline-user-flow
```

## 9. VM operations

### 9.1 GCP authentication
```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud compute instances list
```

### 9.2 Basic VM SSH commands
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b
gcloud compute ssh openclaw-server --zone=us-east1-b --command "hostname"
gcloud compute ssh openclaw-server --zone=us-east1-b --command "pwd; ls /opt; docker ps --format '{{.Names}}'"
gcloud compute ssh openclaw-server --zone=us-east1-b --command "ls -la /opt/gooni"
```

### 9.3 Verify required VM runtime files
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo mkdir -p /opt/gooni /opt/gooni/results && sudo test -f /opt/gooni/admin.env || echo 'Create /opt/gooni/admin.env first'"
```

### 9.4 Verify required env is present inside the running container
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo docker exec gooni-gooni sh -lc 'for k in API_KEY ADMIN_LOGIN ADMIN_PASSWORD_HASH ACCOUNTS_ENCRYPT_KEY HF_TOKEN; do if [ -z \"\${!k}\" ]; then echo \"MISSING: $k\"; else echo \"OK: $k\"; fi; done'"
```

### 9.5 Canonical VM deploy command

This is the exact deploy style used for production updates.

Notes:
- It pulls the latest branch state on the VM
- It rebuilds with `docker build --pull`
- It mounts `/opt/gooni/results`
- It injects `/opt/gooni/admin.env`
- `VITE_API_URL` is only a build-time fallback value; on the VM, the browser uses same-origin `/api`

```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "bash -lc 'set -e; cd ~/gooni-gooni; git fetch --all --prune; git checkout 001-pipeline-user-flow; git pull --ff-only origin 001-pipeline-user-flow; sudo docker build --pull -t gooni-gooni:local --build-arg VITE_API_URL=https://yapparov-emir-f--gooni-api.modal.run .; sudo mkdir -p /opt/gooni/results; sudo test -f /opt/gooni/admin.env; sudo docker stop gooni-gooni >/dev/null 2>&1 || true; sudo docker rm gooni-gooni >/dev/null 2>&1 || true; sudo docker run -d --name gooni-gooni --restart unless-stopped -p 80:80 -v /opt/gooni/results:/results --env-file /opt/gooni/admin.env gooni-gooni:local; sleep 8; sudo docker ps --filter name=gooni-gooni'"
```

### 9.6 Alternate VM deploy helper script
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b -- 'bash -s' < deploy-to-gcp.sh
```

### 9.7 VM verification commands
```bash
curl -i http://34.73.173.191/health
curl -i http://34.73.173.191/api/health
curl -i http://34.73.173.191/
curl -i http://34.73.173.191/admin
```

### 9.8 VM container logs and state
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo docker logs --tail=200 gooni-gooni"
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo docker ps --filter name=gooni-gooni"
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo docker inspect gooni-gooni --format '{{.Image}}'"
```

## 10. Modal operations

### 10.1 Normal production rule
- In the current multi-account production model, use the admin panel to deploy worker accounts
- Preferred buttons:
  - `Deploy`
  - `Redeploy`
  - `Deploy all`

### 10.2 Manual CLI deploy (debug only)
Use only when you intentionally want to debug a single workspace directly:

```bash
modal deploy backend/app.py
VIDEO_GPU=A10G IMAGE_GPU=A10G modal deploy backend/app.py
```

### 10.3 Modal CLI setup and diagnostics
```bash
pip install modal
modal setup
modal profile current
modal app logs gooni-gooni-backend
modal app logs gooni-gooni-backend -f
```

### 10.4 Health check for a specific workspace
Replace `<workspace>`:

```bash
curl -sS https://<workspace>--gooni-api.modal.run/health
curl -i https://<workspace>--gooni-api.modal.run/models -H "X-API-Key: <API_KEY>"
```

## 11. End-to-end verification

### 11.1 Admin login
```bash
curl -i -X POST http://34.73.173.191/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{"login":"<ADMIN_LOGIN>","password":"<ADMIN_PASSWORD>"}'
```

### 11.2 Create generation session
```bash
curl -i -X POST http://34.73.173.191/api/auth/session -c /tmp/gg.cookies
```

### 11.3 Submit generation through the VM gateway
```bash
curl -i -X POST http://34.73.173.191/api/generate \
  -H "Content-Type: application/json" \
  -b /tmp/gg.cookies \
  -d '{"model":"pony","type":"image","mode":"txt2img","prompt":"smoke","width":512,"height":512,"steps":8,"seed":1}'
```

### 11.4 Poll status
```bash
curl -i http://34.73.173.191/api/status/<task_id> -b /tmp/gg.cookies
```

### 11.5 Fetch artifacts through the gateway only
```bash
curl -i http://34.73.173.191/api/results/<task_id> -b /tmp/gg.cookies
curl -i http://34.73.173.191/api/preview/<task_id> -b /tmp/gg.cookies
```

Expected contract:
- `task_id` is opaque to the frontend
- remote task ids use `workspace::task_id`
- status payload includes `task_id`, `status`, `progress`, `stage`, `stage_detail`
- terminal errors use `{code, detail, user_action}`
- browser media URLs must stay gateway-safe: `/api/results/...`, `/api/preview/...`

## 12. PowerShell commands used during live debugging

These are the exact Windows-side commands used to inspect production behavior.

### 12.1 VM health
```powershell
(Invoke-WebRequest -Uri http://34.73.173.191/health -UseBasicParsing).StatusCode
```

### 12.2 Confirm deployed frontend bundle
```powershell
(Invoke-WebRequest -Uri http://34.73.173.191/ -UseBasicParsing).Content |
  Select-String -Pattern "assets/index-.*\.js" |
  ForEach-Object { $_.Matches.Value }
```

### 12.3 Create a browser generation session and inspect task status
```powershell
$base = "http://34.73.173.191"
Invoke-WebRequest -Uri "$base/api/auth/session" -Method Post -SessionVariable s -UseBasicParsing | Out-Null
Invoke-WebRequest -Uri "$base/api/status/<task_id>" -WebSession $s -UseBasicParsing | Select-Object -ExpandProperty Content
```

## 13. Rollback

### 13.1 VM rollback
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "bash -lc 'set -e; cd ~/gooni-gooni; git fetch --all --prune; git checkout <PREVIOUS_GOOD_REF>; sudo docker build --pull -t gooni-gooni:local --build-arg VITE_API_URL=https://yapparov-emir-f--gooni-api.modal.run .; sudo docker stop gooni-gooni >/dev/null 2>&1 || true; sudo docker rm gooni-gooni >/dev/null 2>&1 || true; sudo docker run -d --name gooni-gooni --restart unless-stopped -p 80:80 -v /opt/gooni/results:/results --env-file /opt/gooni/admin.env gooni-gooni:local'"
```

### 13.2 Modal rollback (debug / single workspace only)
```bash
git checkout <PREVIOUS_GOOD_REF>
modal deploy backend/app.py
```

## 14. Common incidents and fixes

### 14.1 Admin login shows `Failed to fetch`
- Check container is running
- Check `/api/health`
- Check `nginx.conf` route `location /api/`

### 14.2 Admin login returns `401` or `403`
- Verify `ADMIN_LOGIN` and `ADMIN_PASSWORD_HASH` in `/opt/gooni/admin.env`
- Restart the VM container after changing the env file

### 14.3 Admin login returns `429`
- This is rate limiting in `admin_security.py`
- Wait for the rate window to clear, or inspect whether failed login attempts are looping

### 14.4 `API_KEY is missing in VM runtime`
- The VM container was started without `--env-file /opt/gooni/admin.env`
- Redeploy using the canonical VM deploy command

### 14.5 New account becomes `failed` immediately
- Check `last_error` in admin UI
- Common causes:
  - missing shared VM env (`API_KEY`, `HF_TOKEN`, etc.)
  - invalid Modal token
  - billing/quota issue
  - worker health-check failure after deploy

### 14.6 Modal `429` / billing errors
- Root cause: workspace spend limit reached
- Action: fix billing in that workspace or remove it from the ready pool
- The VM admin login still works because it is local

### 14.7 Remote task status returns transient `502`
- Frontend now treats `502/503` from `/api/status` as transient and retries
- If the task stays stale for a long time, inspect the target worker workspace logs

### 14.8 "No changes after deploy"
- Confirm git pull happened on the VM
- Confirm `docker build --pull` ran
- Confirm old container was removed
- Confirm a new bundle hash is being served from `/`

## 15. Practical operating rules

- Production browser flow goes through the VM gateway
- Worker accounts are equal; no permanent default account assumption
- Use admin-driven worker deploys in the multi-account model
- Keep VM env file and `/results` mount intact on every redeploy
- Do not store real credentials in this repo

## 16. Zero-to-Prod bootstrap

This section is the missing first-time setup path. Use it when the VM is reachable but the app is not yet installed there, or when you are setting up a fresh production environment.

### 16.1 First-time VM bootstrap

Assumptions:
- the VM instance `openclaw-server` already exists
- you already have SSH access through `gcloud`
- port `80` is reachable from the internet

#### 16.1.1 Verify baseline access
```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud compute ssh openclaw-server --zone=us-east1-b --command "hostname; whoami; pwd"
```

#### 16.1.2 Prepare the application directory on the VM
If the repo is not present on the VM yet:

```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "bash -lc 'command -v git >/dev/null 2>&1 || (sudo apt-get update && sudo apt-get install -y git); test -d ~/gooni-gooni/.git || git clone https://github.com/Codekeeper45/GooniGooni.git ~/gooni-gooni; cd ~/gooni-gooni; git fetch --all --prune; git checkout 001-pipeline-user-flow; git pull --ff-only origin 001-pipeline-user-flow'"
```

If the repo already exists, just update it:

```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "bash -lc 'cd ~/gooni-gooni; git fetch --all --prune; git checkout 001-pipeline-user-flow; git pull --ff-only origin 001-pipeline-user-flow'"
```

#### 16.1.3 Prepare runtime directories
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo mkdir -p /opt/gooni /opt/gooni/results && sudo chown -R $USER:$USER /opt/gooni"
```

### 16.2 Safe creation of `/opt/gooni/admin.env`

This must be done before the first production deploy.

#### 16.2.1 Create the env file interactively on the VM
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b
nano /opt/gooni/admin.env
chmod 600 /opt/gooni/admin.env
```

#### 16.2.2 Minimum required content
```dotenv
API_KEY=<shared_api_key>
ADMIN_LOGIN=<admin_login>
ADMIN_PASSWORD_HASH=<pbkdf2_hash>
ACCOUNTS_ENCRYPT_KEY=<fernet_key>
HF_TOKEN=<huggingface_token>
MODAL_TARGET_ENV=main
ADMIN_COOKIE_SECURE=0
ADMIN_COOKIE_SAMESITE=lax
```

#### 16.2.3 Validate the file exists and is non-empty
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "test -s /opt/gooni/admin.env && echo OK || (echo MISSING_OR_EMPTY; exit 1)"
```

#### 16.2.4 Validate only key names, not values
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "bash -lc 'grep -E \"^(API_KEY|ADMIN_LOGIN|ADMIN_PASSWORD_HASH|ACCOUNTS_ENCRYPT_KEY|HF_TOKEN|MODAL_TARGET_ENV|ADMIN_COOKIE_SECURE|ADMIN_COOKIE_SAMESITE)=\" /opt/gooni/admin.env | sed \"s/=.*$/=<redacted>/\"'"
```

### 16.3 First production deploy on the VM

Once `~/gooni-gooni` and `/opt/gooni/admin.env` exist, use the canonical deploy command from section `9.5`.

Quick path:
```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "bash -lc 'set -e; cd ~/gooni-gooni; git fetch --all --prune; git checkout 001-pipeline-user-flow; git pull --ff-only origin 001-pipeline-user-flow; sudo docker build --pull -t gooni-gooni:local --build-arg VITE_API_URL=https://yapparov-emir-f--gooni-api.modal.run .; sudo mkdir -p /opt/gooni/results; sudo test -f /opt/gooni/admin.env; sudo docker stop gooni-gooni >/dev/null 2>&1 || true; sudo docker rm gooni-gooni >/dev/null 2>&1 || true; sudo docker run -d --name gooni-gooni --restart unless-stopped -p 80:80 -v /opt/gooni/results:/results --env-file /opt/gooni/admin.env gooni-gooni:local; sleep 8; sudo docker ps --filter name=gooni-gooni'"
```

### 16.4 First Modal worker-account bootstrap from the admin panel

This is the correct production path for new worker accounts.

#### 16.4.1 Pre-check before adding the account
The VM must already be deployed and the container must have the shared env:

```bash
gcloud compute ssh openclaw-server --zone=us-east1-b --command "sudo docker exec gooni-gooni sh -lc 'for k in API_KEY ADMIN_LOGIN ADMIN_PASSWORD_HASH ACCOUNTS_ENCRYPT_KEY HF_TOKEN; do if [ -z \"\${!k}\" ]; then echo \"MISSING: $k\"; else echo \"OK: $k\"; fi; done'"
```

If any required key is missing, do not add the account yet. Fix `/opt/gooni/admin.env` first and redeploy the VM.

#### 16.4.2 Add a new account in the admin UI
1. Open `http://34.73.173.191/admin`
2. Log in with `ADMIN_LOGIN` and the password matching `ADMIN_PASSWORD_HASH`
3. In the accounts section, add:
   - `Label`
   - `Workspace`
   - `Token ID`
   - `Token Secret`
4. Submit the form

Expected backend chain:
- account saved as `pending`
- shared secrets synced into the target workspace
- deploy starts
- health-check runs
- account transitions to `ready` or `failed`

#### 16.4.3 First deploy of all available accounts
After adding one or more accounts:
- use `Deploy` for one account
- or use `Deploy all` to deploy every eligible account

Operational rule:
- in the multi-account model, this is the preferred production deploy path for workers
- do not rely on manual `modal deploy backend/app.py` as the normal production procedure

#### 16.4.4 Success criteria for a new worker account
The account is usable only when:
- `status = ready`
- no `last_error`
- it appears in the rotation pool
- a new `/api/generate` request can be dispatched to it

### 16.5 Post-deploy smoke checklist

Use this immediately after first setup or after a major redeploy.

#### 16.5.1 VM smoke checks
```bash
curl -i http://34.73.173.191/health
curl -i http://34.73.173.191/api/health
curl -i http://34.73.173.191/
curl -i http://34.73.173.191/admin
```

Expected:
- `/health` returns `200`
- `/api/health` returns `200`
- site root returns HTML
- `/admin` returns HTML

#### 16.5.2 Admin auth smoke check
```bash
curl -i -X POST http://34.73.173.191/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{"login":"<ADMIN_LOGIN>","password":"<ADMIN_PASSWORD>"}'
```

Expected:
- `204 No Content`
- admin session cookie is set

#### 16.5.3 Generation smoke check
```bash
curl -i -X POST http://34.73.173.191/api/auth/session -c /tmp/gg.cookies
curl -i -X POST http://34.73.173.191/api/generate \
  -H "Content-Type: application/json" \
  -b /tmp/gg.cookies \
  -d '{"model":"pony","type":"image","mode":"txt2img","prompt":"smoke","width":512,"height":512,"steps":8,"seed":1}'
```

Expected:
- generation session returns `204`
- generate returns `200`
- response contains a `task_id`

#### 16.5.4 Status and artifact smoke check
```bash
curl -i http://34.73.173.191/api/status/<task_id> -b /tmp/gg.cookies
curl -i http://34.73.173.191/api/results/<task_id> -b /tmp/gg.cookies
curl -i http://34.73.173.191/api/preview/<task_id> -b /tmp/gg.cookies
```

Expected:
- status progresses from `pending/processing` to `done` or `failed`
- if `done`, result and preview are available via `/api/*`
- browser flow should never require direct access to a Modal workspace URL
