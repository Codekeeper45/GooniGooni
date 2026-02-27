#!/bin/sh
set -eu

mkdir -p /results

# Local admin-only backend for /api/*
export PYTHONPATH="/app/backend:${PYTHONPATH:-}"
uvicorn admin_local:api --host 127.0.0.1 --port 8001 --workers 1 &

# Frontend
exec nginx -g "daemon off;"

