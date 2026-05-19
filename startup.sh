#!/bin/bash
set -euo pipefail

cd /home/site/wwwroot
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8001}

VENV=/tmp/venv

# Resolve the Python 3.11 binary dynamically. Azure App Service Python images
# bundle a specific patch version under /opt/python/3.11.X/bin/python and the
# version changes when the base image rolls (e.g. 3.11.14 → 3.11.15). A
# hardcoded path caused exit code 127 + ContainerTimeout in production when
# the image rolled to 20260504.4.tuxprod. Glob the latest available instead.
PYTHON=$(ls -1d /opt/python/3.11.*/bin/python 2>/dev/null | sort -V | tail -1)
if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
  PYTHON=$(command -v python3.11 || command -v python3 || command -v python || true)
fi
if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
  echo "[startup] FATAL: no Python 3 interpreter found under /opt/python/3.11.* or on PATH" >&2
  exit 1
fi
echo "[startup] Using PYTHON=$PYTHON"

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
