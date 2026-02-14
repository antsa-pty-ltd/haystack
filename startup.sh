#!/bin/bash
set -euo pipefail

cd /home/site/wwwroot
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8001}

VENV=/tmp/venv
PYTHON=/opt/python/3.11.14/bin/python

# CRITICAL: Oryx injects corrupt antenv into PYTHONPATH. Nuke it entirely.
unset PYTHONPATH
export PYTHONPATH=""

# Fast path: venv already built with all packages
if [ -d "$VENV" ] && "$VENV/bin/python" -c "import fastapi, openai, haystack, aiohttp, httpx, pydantic" 2>/dev/null; then
  echo "[startup] Packages OK - starting immediately"
  exec "$VENV/bin/python" -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
fi

# Build fresh venv using absolute Python path (not Oryx-modified PATH)
echo "[startup] Building venv at $VENV..."
rm -rf "$VENV"
"$PYTHON" -m venv "$VENV"

# Force reinstall everything - ignore any packages Oryx/antenv put in the path
"$VENV/bin/pip" install --no-cache-dir --ignore-installed -r requirements.txt
echo "[startup] Done installing packages"

# Verify critical imports
"$VENV/bin/python" -c "import fastapi, openai, haystack, aiohttp, httpx, pydantic"
echo "[startup] All imports verified OK"

echo "[startup] Launching Uvicorn on $HOST:$PORT"
exec "$VENV/bin/python" -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
