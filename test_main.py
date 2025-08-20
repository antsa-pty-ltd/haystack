from fastapi import FastAPI

app = FastAPI(title="Haystack Test API", version="1.0.0")

@app.get("/")
async def root():
    return {"message": "Haystack AU service is running!", "status": "healthy"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "haystack-au-production"}

@app.get("/docs")
async def get_docs():
    return {"docs": "Available at /docs endpoint"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
