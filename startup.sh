#!/bin/bash
set -euo pipefail

cd /home/site/wwwroot
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8001}

VENV=/tmp/venv

# Use /tmp (local SSD) for the venv - much faster than Azure Files
# The venv is rebuilt on each container start but takes ~5 min on local disk
if [ -d "$VENV" ] && "$VENV/bin/python" -c "import fastapi, openai, haystack, aiohttp" 2>/dev/null; then
  echo "[startup] Packages OK - starting immediately"
else
  echo "[startup] Building venv at $VENV (local SSD)..."
  rm -rf "$VENV"
  python -m venv "$VENV"
  "$VENV/bin/pip" install --no-cache-dir -r requirements.txt
  echo "[startup] Done installing packages"
fi

echo "[startup] Launching Uvicorn on $HOST:$PORT"
exec "$VENV/bin/python" -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
