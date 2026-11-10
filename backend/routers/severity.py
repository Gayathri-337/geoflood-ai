"""GeoFlood AI backend - flood severity of an analysis."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.severity import SeverityOut
from backend.security import MAX_BIGINT
from backend.services import analysis_service, impact_service
from backend.services import severity as severity_rules

router = APIRouter(prefix="/analyses", tags=["severity"])


def _classify(db: Session, analysis_id: int):
    analysis = analysis_service.fetch_analysis(db, analysis_id)
    if analysis is None:
        raise HTTPException(404, f"Analysis {analysis_id} not found")
    zone = impact_service.resolve_zone(analysis["baseline_method"], None)
    summary = impact_service.summarize(db, analysis_id, zone)
    return analysis, severity_rules.classify(analysis, summary)


@router.get("/{analysis_id}/severity", response_model=SeverityOut)
def get_severity(analysis_id: int = PathParam(ge=1, le=MAX_BIGINT), db: Session = Depends(get_db)):
    """
    The severity worked out from the analysis and its stored impact results. Nothing is saved.
    The rules are provisional (see backend/services/severity.py).
    """
    analysis, result = _classify(db, analysis_id)
    return {**result, "analysis_id": analysis_id, "stored_severity": analysis["severity"]}


@router.post("/{analysis_id}/severity", response_model=SeverityOut)
def save_severity(analysis_id: int = PathParam(ge=1, le=MAX_BIGINT), db: Session = Depends(get_db)):
    """Work out the severity and save it as the analysis's severity."""
    analysis, result = _classify(db, analysis_id)
    db.execute(text("UPDATE flood_analysis SET severity = :level WHERE analysis_id = :id"),
               {"level": result["level"], "id": analysis_id})
    db.commit()
    return {**result, "analysis_id": analysis_id, "stored_severity": result["level"]}
