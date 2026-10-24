"""GeoFlood AI backend - satellite sources."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.orm import SatelliteSource
from backend.schemas.sources import SourceOut

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)):
    """All imagery sources, in the order they were added."""
    return db.scalars(select(SatelliteSource).order_by(SatelliteSource.source_id)).all()
