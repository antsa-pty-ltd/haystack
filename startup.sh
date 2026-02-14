#!/bin/bash
set -euo pipefail

cd /home/site/wwwroot
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8001}
PACKAGES=/tmp/pypackages

# Install packages to /tmp (fast local SSD, not slow Azure Files)
# This is rebuilt on each container start but takes only ~60s on local disk
if python -c "import sys; sys.path.insert(0,'$PACKAGES'); import fastapi, openai, haystack" 2>/dev/null; then
  echo "[startup] Packages already installed"
else
  echo "[startup] Installing packages to $PACKAGES..."
  pip install --no-cache-dir --target "$PACKAGES" -r requirements.txt -q
  echo "[startup] Done installing packages"
fi

export PYTHONPATH="$PACKAGES:${PYTHONPATH:-}"

echo "[startup] Launching Uvicorn on $HOST:$PORT"
exec python -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
