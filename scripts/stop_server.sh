#!/bin/bash
set -e

echo "Stopping haystack-service..."

# Stop the service using supervisor
if supervisorctl status haystack-service > /dev/null 2>&1; then
    supervisorctl stop haystack-service
    echo "haystack-service stopped successfully"
else
    echo "haystack-service was not running"
fi