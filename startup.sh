#!/bin/bash
set -euo pipefail

cd /home/site/wwwroot
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8001}

VENV=antenv

# Fast path: venv exists and works -> start immediately
if [ -d "$VENV" ] && "$VENV/bin/python" -c "import fastapi, openai, haystack" 2>/dev/null; then
  echo "[startup] Packages OK - starting immediately"
  exec "$VENV/bin/python" -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
fi

# First-time or recovery: build fresh venv
echo "[startup] Building virtual environment (first-time setup)..."
rm -rf "$VENV"
python -m venv "$VENV"
"$VENV/bin/pip" install --no-cache-dir -r requirements.txt
echo "[startup] Venv built successfully"

exec "$VENV/bin/python" -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
