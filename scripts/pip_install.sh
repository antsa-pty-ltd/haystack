#!/bin/bash
set -e

echo "Starting pip_install script..."

cd /var/www/html/antsa-live/haystack-service

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3.11 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
python -m pip install --upgrade pip

# Install requirements
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Set proper permissions
chown -R ubuntu:ubuntu /var/www/html/antsa-live/haystack-service

echo "pip_install script completed successfully"