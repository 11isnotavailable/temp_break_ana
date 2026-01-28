import uvicorn
from fastapi import FastAPI
from app.api.endpoints import router as api_router

app = FastAPI(title="Industrial Agent Service")

app.include_router(api_router, prefix="/v1/analysis")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)