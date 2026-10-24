"""GeoFlood AI backend - health checks."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db

router = APIRouter(tags=["health"])

EXPECTED_TABLES = {
    "users", "satellite_sources", "disaster_events", "satellite_images", "flood_analysis",
    "flood_zones", "reference_features", "affected_villages", "affected_roads",
    "agricultural_areas", "critical_infrastructure", "flood_reports", "emergency_actions",
}


@router.get("/health")
def health():
    """Is the API process running? (does not touch the database)"""
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name, "version": settings.app_version}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    """Can the API reach PostgreSQL, is PostGIS enabled, and are all 13 tables present?"""
    database = db.execute(text("SELECT current_database()")).scalar_one()
    postgis = db.execute(text("SELECT PostGIS_Version()")).scalar_one()
    found = set(db.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")).scalars())
    missing = sorted(EXPECTED_TABLES - found)
    return {
        "status": "ok" if not missing else "incomplete",
        "database": database,
        "postgis_version": postgis,
        "tables_present": len(EXPECTED_TABLES & found),
        "missing_tables": missing,
    }
