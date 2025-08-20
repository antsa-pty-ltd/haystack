import os
from fastapi import FastAPI

app = FastAPI(title="Haystack AU Production", version="1.0.0")

@app.get("/")
async def root():
    return {
        "message": "Haystack AU service is running!",
        "status": "healthy", 
        "port": os.getenv("PORT", "not_set"),
        "service": "antsa-haystack-au-production",
        "deployment": "fresh_service"
    }

@app.get("/health")  
async def health_check():
    return {
        "status": "healthy",
        "service": "haystack-au-production", 
        "environment": "azure-app-service-fresh"
    }

@app.get("/test")
async def test_endpoint():
    return {
        "message": "Fresh Azure App Service test successful!",
        "imports": "basic_only",
        "dependencies": ["fastapi", "uvicorn"]
    }
