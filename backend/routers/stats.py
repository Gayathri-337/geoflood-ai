"""GeoFlood AI backend - numbers for the dashboard."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.analysis import DashboardOut

router = APIRouter(prefix="/stats", tags=["statistics"])

NOTE = ("Totals add up separate analyses. If two analyses cover the same ground, that area is "
        "counted twice. New-flood totals include only analyses that had a baseline layer.")


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT (SELECT count(*) FROM disaster_events)                      AS events,
               (SELECT count(*) FROM satellite_images)                     AS images,
               (SELECT count(*) FROM flood_zones)                          AS zone_polygons,
               count(*) FILTER (WHERE status = 'completed')                AS analyses_completed,
               count(*) FILTER (WHERE status = 'completed' AND baseline_method <> 'none')
                                                                           AS analyses_with_baseline,
               coalesce(sum(water_area_km2) FILTER (WHERE status = 'completed'), 0)
                                                                           AS total_water_area_km2,
               coalesce(sum(permanent_water_area_km2) FILTER (WHERE status = 'completed'), 0)
                                                                           AS total_permanent_water_area_km2,
               coalesce(sum(new_flood_area_km2) FILTER (WHERE status = 'completed'), 0)
                                                                           AS total_new_flood_area_km2,
               max(created_at)                                             AS latest_analysis_at
          FROM flood_analysis""")).mappings().one()
    out = dict(row)
    for key in ("total_water_area_km2", "total_permanent_water_area_km2", "total_new_flood_area_km2"):
        out[key] = float(out[key])
    out["note"] = NOTE
    return out
