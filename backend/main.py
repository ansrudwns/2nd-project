from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.exceptions import AnalysisException
from app.schemas.common import BaseResponse
from app.api.endpoints import analysis

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handler
@app.exception_handler(AnalysisException)
async def analysis_exception_handler(request: Request, exc: AnalysisException):
    return JSONResponse(
        status_code=400,
        content=exc.to_dict()
    )

from fastapi.staticfiles import StaticFiles
import os

# Create uploads dir
os.makedirs("uploads", exist_ok=True)

app.mount("/static", StaticFiles(directory="uploads"), name="static")

app.include_router(analysis.router, prefix=settings.API_V1_STR, tags=["Analysis"])
from app.api.endpoints import auth
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["Auth"])
from app.api.endpoints import history
app.include_router(history.router, prefix=f"{settings.API_V1_STR}/history", tags=["History"])

from app.db.init_db import init_db
@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/")
def read_root():
    return {"message": "Real Estate Analysis System API is running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
