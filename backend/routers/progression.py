"""GeoFlood AI backend - flood progression of an event (Phase 29a)."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.security import MAX_BIGINT
from backend.services.progression import build_progression

router = APIRouter(prefix="/events", tags=["progression"])

LOAD = text("""
    SELECT a.analysis_id, i.file_name AS original_filename, i.acquired_at, a.created_at, a.status,
           a.water_area_km2, a.water_pct_of_valid, a.valid_area_km2, a.baseline_method,
           ST_XMin(i.footprint) AS west, ST_YMin(i.footprint) AS south,
           ST_XMax(i.footprint) AS east, ST_YMax(i.footprint) AS north
    FROM flood_analysis a
    JOIN satellite_images i ON i.image_id = a.image_id
    WHERE i.event_id = :event_id
    ORDER BY a.analysis_id""")


@router.get("/{event_id}/progression")
def event_progression(event_id: int = PathParam(ge=1, le=MAX_BIGINT), db: Session = Depends(get_db)):
    """
    How the detected water changes between images of the SAME AREA on DIFFERENT DATES in one event.
    Analyses without an observation date, or without a second date for the same area, are not compared:
    they are listed under 'unassigned' with the reason. Nothing is stored or changed.
    """
    if db.execute(text("SELECT 1 FROM disaster_events WHERE event_id = :id"), {"id": event_id}).first() is None:
        raise HTTPException(404, f"Event {event_id} not found")
    analyses = []
    for row in db.execute(LOAD, {"event_id": event_id}).mappings():
        item = dict(row)
        item["bounds_wgs84"] = [float(item.pop(k)) for k in ("west", "south", "east", "north")]
        analyses.append(item)
    return build_progression(analyses, event_id=event_id)
