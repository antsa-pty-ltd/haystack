#!/bin/bash
cd /home/site/wwwroot
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8001}
echo "[startup] Starting Uvicorn on $HOST:$PORT"
exec antenv/bin/python -m uvicorn main:app --host "$HOST" --port "$PORT" --log-level info
