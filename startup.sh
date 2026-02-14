#!/bin/bash
set -euo pipefail

export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8001}
export VENV_DIR=${VENV_DIR:-"$PWD/antenv"}

echo "[startup] Using Python: $(python --version 2>/dev/null || echo 'not found')"
echo "[startup] Virtual env at: $VENV_DIR"

# Oryx installs packages during deployment (SCM_DO_BUILD_DURING_DEPLOYMENT=true).
# Do NOT run pip install at runtime - it takes too long and causes startup probe timeouts.
# If the venv doesn't exist, Oryx didn't build properly - fall back to system python.
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ]; then
  echo "[startup] Using Oryx-built virtual environment"
  PYTHON="$VENV_DIR/bin/python"
else
  echo "[startup] WARNING: No virtual environment found, using system Python"
  PYTHON="python"
fi

echo "[startup] Launching Uvicorn on $HOST:$PORT"
exec $PYTHON -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
