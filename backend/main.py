
"""
GeoFlood AI backend - application entry point.

Run (from the project root):
    uvicorn backend.main:app --reload

Interactive docs:
    http://127.0.0.1:8000/docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.config import get_settings
from backend.routers import (
    actions,
    analyses,
    auth,
    events,
    health,
    impact,
    predict,
    report,
    severity,
    sources,
    stats,
    users,
)
from backend.security import access_policy
from backend.services.inference import ModelService
from backend.services.uploads import UploadRejected


settings = get_settings()
log = logging.getLogger("geoflood")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the U-Net model when the application starts."""
    app.state.model_service.load()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "API for GeoFlood AI: water and flood mapping "
        "from Sentinel-1 radar imagery."
    ),
    lifespan=lifespan,
)

app.state.model_service = ModelService(settings.model_checkpoint)


# ------------------------------------------------------------
# CORS configuration
# ------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------
# Exception handlers
# ------------------------------------------------------------

@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    """Return a generic database error without exposing internal details."""
    log.exception(
        "Database error on %s %s",
        request.method,
        request.url.path,
    )

    return JSONResponse(
        status_code=503,
        content={
            "detail": "The database is unavailable or returned an error."
        },
    )


@app.exception_handler(UploadRejected)
async def upload_rejected_handler(
    request: Request,
    exc: UploadRejected,
):
    """Return the appropriate error for a rejected upload."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# ------------------------------------------------------------
# Public routers
# ------------------------------------------------------------
# Health checks and authentication are public.
# The users router applies its own administrator-only rules.

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")


# ------------------------------------------------------------
# Protected routers
# ------------------------------------------------------------
# A central access policy is applied to all data-related routers.
# The report router is included here so PDF downloads require login.

policy = [Depends(access_policy)]

app.include_router(
    sources.router,
    prefix="/api",
    dependencies=policy,
)

app.include_router(
    events.router,
    prefix="/api",
    dependencies=policy,
)

app.include_router(
    predict.router,
    prefix="/api",
    dependencies=policy,
)

app.include_router(
    analyses.router,
    prefix="/api",
    dependencies=policy,
)

app.include_router(
    impact.router,
    prefix="/api",
    dependencies=policy,
)

app.include_router(
    severity.router,
    prefix="/api",
    dependencies=policy,
)

app.include_router(
    actions.router,
    prefix="/api",
    dependencies=policy,
)

app.include_router(
    stats.router,
    prefix="/api",
    dependencies=policy,
)

app.include_router(
    report.router,
    prefix="/api",
    dependencies=policy,
)


# ------------------------------------------------------------
# Root endpoint
# ------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root():
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": "/api/health",
    }
