"""GeoFlood AI backend - impact of an analysis on villages, roads, farmland and infrastructure."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.impact import ImpactRunOut, ImpactSummaryOut
from backend.services import impact_service as svc

router = APIRouter(prefix="/analyses", tags=["impact"])

MAX_BIGINT = 2 ** 63 - 1
MAX_NEAR_M = 10_000
Layer = Literal["villages", "roads", "farmland", "infrastructure"]
ImpactZone = Literal["water", "new_flood"]

SUMMARY_NOTE = ("Zero everywhere can mean either that impact has not been computed yet or that nothing "
                "was affected: check last_computed_at (null when no results are stored).")


def _baseline_or_404(db: Session, analysis_id: int) -> str:
    method = svc.baseline_of(db, analysis_id)
    if method is None:
        raise HTTPException(404, f"Analysis {analysis_id} not found")
    return method


@router.post("/{analysis_id}/impact", response_model=ImpactRunOut)
def compute_impact(
    analysis_id: int = PathParam(ge=1, le=MAX_BIGINT),
    near_m: float = Query(500, ge=0, le=MAX_NEAR_M,
                          description="villages and infrastructure within this many metres of the "
                                      "flood count as 'near'"),
    zone_type: Optional[ImpactZone] = Query(
        None, description="what to compare against; default: new_flood if the analysis has a "
                          "baseline, otherwise water"),
    db: Session = Depends(get_db),
):
    """
    Find the villages, roads, farmland and infrastructure affected by an analysis, and store them.
    Running it again replaces the earlier results for the same zone type.
    """
    zone = svc.resolve_zone(_baseline_or_404(db, analysis_id), zone_type)
    counts = svc.run_compute(db, analysis_id, zone, near_m)
    db.commit()
    return {"analysis_id": analysis_id, "zone_type": zone,
            "compared_against": svc.COMPARED_AGAINST[zone], "near_m": near_m, **counts}


@router.get("/{analysis_id}/impact", response_model=ImpactSummaryOut)
def impact_summary(
    analysis_id: int = PathParam(ge=1, le=MAX_BIGINT),
    zone_type: Optional[ImpactZone] = Query(None),
    db: Session = Depends(get_db),
):
    """Counts and totals of the stored impact results (the numbers for the dashboard)."""
    baseline = _baseline_or_404(db, analysis_id)
    zone = svc.resolve_zone(baseline, zone_type)
    return {"analysis_id": analysis_id, "zone_type": zone,
            "compared_against": svc.COMPARED_AGAINST[zone], "baseline_method": baseline,
            "note": SUMMARY_NOTE, **svc.summarize(db, analysis_id, zone)}


@router.get("/{analysis_id}/impact/{layer}")
def impact_layer(
    analysis_id: int = PathParam(ge=1, le=MAX_BIGINT),
    layer: Layer = PathParam(),
    zone_type: Optional[ImpactZone] = Query(None),
    db: Session = Depends(get_db),
):
    """
    The affected features of one layer as GeoJSON (longitude/latitude).
    For roads and farmland the geometry is only the flooded part of each feature.
    """
    zone = svc.resolve_zone(_baseline_or_404(db, analysis_id), zone_type)
    return JSONResponse(svc.layer_geojson(db, analysis_id, zone, layer), media_type="application/geo+json")
