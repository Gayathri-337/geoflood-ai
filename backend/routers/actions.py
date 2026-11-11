"""GeoFlood AI backend - emergency actions of an event."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.actions import ActionCreate, ActionOut, ActionType, ActionUpdate, Priority, Status
from backend.security import MAX_BIGINT, require_admin
from backend.services import actions as svc

router = APIRouter(tags=["emergency actions"])

NO_SUCH_ASSIGNEE = "The person to assign does not exist or is disabled."


def _require_event(db: Session, event_id: int) -> None:
    if not svc.event_exists(db, event_id):
        raise HTTPException(404, f"Event {event_id} not found")


def _require_assignee(db: Session, user_id: Optional[int]) -> None:
    if user_id is not None and not svc.user_is_active(db, user_id):
        raise HTTPException(422, NO_SUCH_ASSIGNEE)


@router.get("/events/{event_id}/actions", response_model=list[ActionOut])
def list_actions(
    event_id: int = PathParam(ge=1, le=MAX_BIGINT),
    status: Optional[Status] = Query(None),
    priority: Optional[Priority] = Query(None),
    action_type: Optional[ActionType] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Open actions first, then by priority, then by due time."""
    _require_event(db, event_id)
    filters = {"status": status, "priority": priority, "action_type": action_type}
    return svc.list_actions(db, event_id, filters, limit, offset)


@router.get("/events/{event_id}/actions/geojson")
def actions_geojson(event_id: int = PathParam(ge=1, le=MAX_BIGINT), db: Session = Depends(get_db)):
    """The actions that have a map pin, as GeoJSON points (longitude, latitude)."""
    _require_event(db, event_id)
    return JSONResponse(svc.locations_geojson(db, event_id), media_type="application/geo+json")


@router.post("/events/{event_id}/actions", response_model=ActionOut, status_code=201)
def create_action(
    payload: ActionCreate,
    request: Request,
    event_id: int = PathParam(ge=1, le=MAX_BIGINT),
    db: Session = Depends(get_db),
):
    _require_event(db, event_id)
    _require_assignee(db, payload.assigned_to)
    user = getattr(request.state, "user", None)        # set by the access rules when someone is logged in
    action_id = svc.create_action(db, event_id, payload.model_dump(), created_by=user.user_id if user else None)
    db.commit()
    return svc.get_action(db, action_id)


@router.patch("/actions/{action_id}", response_model=ActionOut)
def update_action(
    payload: ActionUpdate,
    action_id: int = PathParam(ge=1, le=MAX_BIGINT),
    db: Session = Depends(get_db),
):
    """Change only the fields that are sent. Send null to clear description, location, assigned_to or due_at."""
    changes = {name: getattr(payload, name) for name in payload.model_fields_set}
    if not changes:
        raise HTTPException(422, "Nothing to update: send at least one field.")
    if svc.get_action(db, action_id) is None:
        raise HTTPException(404, f"Action {action_id} not found")
    _require_assignee(db, changes.get("assigned_to"))
    if "location" in changes and changes["location"] is not None:
        changes["location"] = {"longitude": changes["location"].longitude, "latitude": changes["location"].latitude}
    svc.update_action(db, action_id, changes)
    db.commit()
    return svc.get_action(db, action_id)


@router.delete("/actions/{action_id}", status_code=204, response_class=Response, dependencies=[Depends(require_admin)])
def delete_action(action_id: int = PathParam(ge=1, le=MAX_BIGINT), db: Session = Depends(get_db)):
    """Admins only. Analysts set the status to 'cancelled' instead."""
    if not svc.delete_action(db, action_id):
        raise HTTPException(404, f"Action {action_id} not found")
    db.commit()
    return Response(status_code=204)
