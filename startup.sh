#!/bin/bash
set -euo pipefail

cd /home/site/wwwroot
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8001}

echo "[startup] Starting Haystack service"
echo "[startup] Python: $(antenv/bin/python --version 2>&1)"
echo "[startup] Launching Uvicorn on $HOST:$PORT"

exec antenv/bin/python -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
