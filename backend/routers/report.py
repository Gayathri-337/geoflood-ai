"""GeoFlood AI backend - the PDF report of an analysis (Phase 28)."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi import Path as PathParam
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.orm import DisasterEvent
from backend.security import MAX_BIGINT
from backend.services import actions as actions_service
from backend.services import analysis_service, impact_service
from backend.services import severity as severity_rules
from backend.services.report import build_report

router = APIRouter(prefix="/analyses", tags=["report"])

EVENT_FIELDS = ("name", "region_name", "country", "status", "start_date", "end_date", "description")


def _zones(db: Session, analysis_id: int) -> dict:
    """The flood polygons as GeoJSON (the same data as GET /analyses/{id}/zones)."""
    rows = db.execute(text("SELECT zone_type, area_km2, ST_AsGeoJSON(geom, 6) AS geojson FROM flood_zones "
                           "WHERE analysis_id = :aid ORDER BY zone_type, poly_no"), {"aid": analysis_id}).mappings()
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": json.loads(r["geojson"]),
         "properties": {"zone_type": r["zone_type"], "area_km2": float(r["area_km2"])}} for r in rows]}


def collect_report_data(db: Session, analysis_id: int, generated_by=None) -> dict:
    """Everything the report shows, read from the stored results. Nothing is computed or saved here."""
    analysis = analysis_service.fetch_analysis(db, analysis_id)
    if analysis is None:
        raise HTTPException(404, f"Analysis {analysis_id} not found")

    event = db.get(DisasterEvent, analysis["event_id"])
    image = db.execute(text("SELECT s.name AS source_name, i.acquired_at FROM satellite_images i "
                            "JOIN satellite_sources s ON s.source_id = i.source_id WHERE i.image_id = :id"),
                       {"id": analysis["image_id"]}).mappings().first() or {}

    zone = impact_service.resolve_zone(analysis["baseline_method"], None)
    summary = impact_service.summarize(db, analysis_id, zone)
    summary.update(zone_type=zone, compared_against=impact_service.COMPARED_AGAINST[zone],
                   baseline_method=analysis["baseline_method"])
    computed = summary["last_computed_at"] is not None
    layers = ({name: impact_service.layer_geojson(db, analysis_id, zone, name) for name in impact_service.LAYER_SQL}
              if computed else None)

    return {
        "generated_at": datetime.now(timezone.utc), "generated_by": generated_by,
        "analysis": analysis,
        "event": {field: getattr(event, field, None) for field in EVENT_FIELDS} if event else {},
        "source_name": image.get("source_name"), "acquired_at": image.get("acquired_at"),
        "zones": _zones(db, analysis_id),
        "impact": {"summary": summary, "layers": layers},
        "coverage": impact_service.reference_coverage(db, analysis_id),
        "severity": severity_rules.classify(analysis, summary),
        "actions": actions_service.list_actions(db, analysis["event_id"], {}, 500, 0),
    }


@router.get("/{analysis_id}/report.pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}, "description": "The report as a PDF file"}})
def download_report(
    request: Request,
    analysis_id: int = PathParam(ge=1, le=MAX_BIGINT),
    db: Session = Depends(get_db),
):
    """
    A PDF report of one analysis: event, image, detected water, flood extent map, severity, infrastructure
    impact, the event's emergency actions and the limitations. It uses the stored results only, so compute the
    impact first (analysis page) if the impact figures should be included. Any logged-in user may download it.
    """
    user = getattr(request.state, "user", None)
    data = collect_report_data(db, analysis_id, generated_by=user.username if user else None)
    pdf = build_report(data)
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="geoflood_analysis_{analysis_id}_report.pdf"',
        "Cache-Control": "no-store",
    })
