#!/bin/bash
set -euo pipefail

export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8001}
export VENV_DIR=${VENV_DIR:-"$PWD/antenv"}

echo "[startup] Using Python: $(python --version 2>/dev/null || echo 'not found')"
echo "[startup] Ensuring virtualenv at: $VENV_DIR"

if [ ! -d "$VENV_DIR" ]; then
  echo "[startup] Creating virtual environment..."
  python -m venv "$VENV_DIR"
fi

# Only install requirements if key packages are missing.
# Oryx already installs them during deployment - avoid duplicate pip install
# which can cause the startup probe to timeout (230s).
if ! "$VENV_DIR/bin/python" -c "import fastapi; import openai; import haystack" 2>/dev/null; then
  echo "[startup] Key packages missing, installing requirements..."
  "$VENV_DIR/bin/pip" install --no-cache-dir -r requirements.txt
else
  echo "[startup] Packages already installed by Oryx, skipping pip install"
fi

echo "[startup] Launching Uvicorn on $HOST:$PORT"
exec "$VENV_DIR/bin/python" -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
