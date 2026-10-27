"""
GeoFlood AI backend - application entry point.

Run (from the project root):   uvicorn backend.main:app --reload
Interactive docs:              http://127.0.0.1:8000/docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.config import get_settings
from backend.routers import analyses, events, health, predict, sources, stats
from backend.services.inference import ModelService
from backend.services.uploads import UploadRejected

settings = get_settings()
log = logging.getLogger("geoflood")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at server start: load the U-Net so requests don't pay for it."""
    app.state.model_service.load()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API for GeoFlood AI: water and flood mapping from Sentinel-1 radar imagery.",
    lifespan=lifespan,
)
app.state.model_service = ModelService(settings.model_checkpoint)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    """Any database failure becomes a generic 503. Details go to the server log, not the client."""
    log.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=503,
                        content={"detail": "The database is unavailable or returned an error."})


@app.exception_handler(UploadRejected)
async def upload_rejected_handler(request: Request, exc: UploadRejected):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(health.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(predict.router, prefix="/api")
app.include_router(analyses.router, prefix="/api")
app.include_router(stats.router, prefix="/api")


@app.get("/", include_in_schema=False)
def root():
    return {"service": settings.app_name, "docs": "/docs", "health": "/api/health"}