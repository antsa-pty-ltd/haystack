#!/bin/bash
set -euo pipefail

export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8000}
export VENV_DIR=${VENV_DIR:-"$PWD/antenv"}

echo "[startup] Using Python: $(python --version 2>/dev/null || echo 'not found')"
echo "[startup] Ensuring virtualenv at: $VENV_DIR"

if [ ! -d "$VENV_DIR" ]; then
  echo "[startup] Creating virtual environment..."
  python -m venv "$VENV_DIR"
fi

echo "[startup] Upgrading pip..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null

if [ -f requirements.txt ]; then
  echo "[startup] Installing requirements..."
  "$VENV_DIR/bin/pip" install --no-cache-dir -r requirements.txt
fi

echo "[startup] Launching Uvicorn on $HOST:$PORT"
exec "$VENV_DIR/bin/python" -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
