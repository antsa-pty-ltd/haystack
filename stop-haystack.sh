#!/bin/bash
pkill -f "uvicorn main:app.*8001" && echo "Haystack stopped" || echo "Haystack is not running"