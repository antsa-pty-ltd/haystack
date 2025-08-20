import os
from fastapi import FastAPI

app = FastAPI(title="Haystack AU Service", version="1.0.0")

@app.get("/")
async def root():
    return {
        "message": "Haystack AU service is running!", 
        "status": "healthy",
        "port": os.getenv("PORT", "not_set"),
        "service": "antsa-haystack-au-production"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "service": "haystack-au-production",
        "environment": "azure-app-service"
    }

@app.get("/test")
async def test_endpoint():
    return {
        "message": "Test endpoint working",
        "imports": "basic_only",
        "dependencies": ["fastapi", "uvicorn"]
    }

# No if __name__ == "__main__" block - let uvicorn command handle it
