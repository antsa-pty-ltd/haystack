#!/bin/bash
set -e

echo "Starting haystack-service..."

cd /var/www/html/antsa-live/haystack-service

# Activate virtual environment
source venv/bin/activate

# Create supervisor configuration for the service
cat > /etc/supervisor/conf.d/haystack-service.conf << EOF
[program:haystack-service]
command=/var/www/html/antsa-live/haystack-service/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
directory=/var/www/html/antsa-live/haystack-service
user=ubuntu
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/haystack-service.log
environment=PATH="/var/www/html/antsa-live/haystack-service/venv/bin"
EOF

# Reload supervisor and start the service
supervisorctl reread
supervisorctl update
supervisorctl restart haystack-service

echo "haystack-service started successfully"