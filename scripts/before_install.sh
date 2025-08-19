#!/bin/bash
set -e

echo "Starting before_install script for haystack-service..."

# Update system packages
apt-get update -y

# Install Python 3.11 if not already installed
if ! command -v python3.11 &> /dev/null; then
    echo "Installing Python 3.11..."
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
    apt-get install -y python3.11 python3.11-pip python3.11-venv python3.11-dev
fi

# Install system dependencies
apt-get install -y supervisor nginx

# Create application directory if it doesn't exist
mkdir -p /var/www/html/antsa-live/haystack-service

# Set proper permissions
chown -R ubuntu:ubuntu /var/www/html/antsa-live/haystack-service

echo "before_install script completed successfully"