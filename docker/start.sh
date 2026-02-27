#!/bin/sh
set -eu

mkdir -p /results

# Local admin API for same-origin /api/*
export PYTHONPATH="/app/backend:${PYTHONPATH:-}"
uvicorn admin_local:api --host 127.0.0.1 --port 8001 --workers 1 &

# Frontend static server
exec nginx -g "daemon off;"
