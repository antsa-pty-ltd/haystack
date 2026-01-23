#!/bin/bash
cd "$(dirname "$0")"

# Check if already running
if pgrep -f "uvicorn main:app.*8001" > /dev/null; then
    echo "Haystack is already running"
    exit 0
fi

# Start the service
source venv/bin/activate
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8001 --workers 1 --limit-concurrency 10 --log-level info > haystack.log 2>&1 &

echo "Haystack started on http://localhost:8001"
echo "Logs: tail -f haystack.log"