#!/bin/bash

# Start script for Haystack AI Service

echo "🚀 Starting Haystack AI Service..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📋 Installing dependencies..."
pip install -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️ No .env file found. Creating from example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "📝 Please edit .env file with your configuration"
    else
        echo "🔑 Please create .env file with required environment variables"
        echo "OPENAI_API_KEY=your_key_here"
        echo "REDIS_URL=redis://localhost:6379"
        echo "DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dbname"
    fi
fi

# Start the service
echo "✅ Starting FastAPI service on port 8001..."
uvicorn main:app --host 0.0.0.0 --port 8001 --reload