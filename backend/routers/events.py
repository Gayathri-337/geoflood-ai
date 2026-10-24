"""GeoFlood AI backend - disaster events."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.orm import DisasterEvent
from backend.schemas.events import EventCreate, EventOut

router = APIRouter(prefix="/events", tags=["events"])

MAX_BIGINT = 2 ** 63 - 1


@router.get("", response_model=list[EventOut])
def list_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Events, newest first."""
    stmt = select(DisasterEvent).order_by(DisasterEvent.event_id.desc()).limit(limit).offset(offset)
    return db.scalars(stmt).all()


@router.post("", response_model=EventOut, status_code=201)
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    event = DisasterEvent(**payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)          # loads event_id and created_at, which the database generated
    return event


@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: int = Path(ge=1, le=MAX_BIGINT), db: Session = Depends(get_db)):
    event = db.get(DisasterEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return event
