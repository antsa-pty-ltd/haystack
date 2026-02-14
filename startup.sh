#!/bin/bash
set -euo pipefail

export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8001}
export VENV_DIR=${VENV_DIR:-"$PWD/antenv"}

echo "[startup] Using Python: $(python --version 2>/dev/null || echo 'not found')"
echo "[startup] Virtual env at: $VENV_DIR"

# Fast path: venv exists and packages are importable → start immediately
if [ -d "$VENV_DIR" ] && "$VENV_DIR/bin/python" -c "import fastapi; import openai; import haystack" 2>/dev/null; then
  echo "[startup] Packages OK, starting Uvicorn"
  exec "$VENV_DIR/bin/python" -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
fi

# Recovery path: venv missing or corrupt → nuke and rebuild
echo "[startup] Venv missing or corrupt, rebuilding..."
rm -rf "$VENV_DIR"
python -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --no-cache-dir -r requirements.txt

echo "[startup] Launching Uvicorn on $HOST:$PORT"
exec "$VENV_DIR/bin/python" -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
