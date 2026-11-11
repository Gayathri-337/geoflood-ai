"""GeoFlood AI backend - emergency actions. All SQL for the emergency_actions table lives here."""

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

SELECT = """
    SELECT a.action_id, a.event_id, a.title, a.description, a.action_type, a.priority, a.status,
           ST_X(a.location) AS longitude, ST_Y(a.location) AS latitude,
           a.assigned_to, u.username AS assigned_to_username, a.created_by,
           a.due_at, a.created_at, a.updated_at
      FROM emergency_actions a
      LEFT JOIN users u ON u.user_id = a.assigned_to
"""

# open actions first, then critical before low, then the earliest due time, then the newest
ORDER = """
    ORDER BY (a.status IN ('completed', 'cancelled')),
             CASE a.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
             a.due_at NULLS LAST, a.action_id DESC
"""

# a point from :lon and :lat, or NULL when they are NULL
POINT = ("CASE WHEN CAST(:lon AS double precision) IS NULL THEN NULL "
         "ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision), CAST(:lat AS double precision)), 4326) END")

UPDATABLE = ("title", "description", "action_type", "priority", "status", "due_at", "assigned_to")  # fixed names
FILTERS = ("status", "priority", "action_type")                                                     # fixed names


def event_exists(db: Session, event_id: int) -> bool:
    return db.execute(text("SELECT 1 FROM disaster_events WHERE event_id = :id"), {"id": event_id}).first() is not None


def user_is_active(db: Session, user_id: int) -> bool:
    return db.execute(text("SELECT 1 FROM users WHERE user_id = :id AND is_active"), {"id": user_id}).first() is not None


def get_action(db: Session, action_id: int) -> Optional[dict]:
    row = db.execute(text(SELECT + " WHERE a.action_id = :id"), {"id": action_id}).mappings().first()
    return dict(row) if row else None


def list_actions(db: Session, event_id: int, filters: dict, limit: int, offset: int) -> list[dict]:
    where, params = ["a.event_id = :event_id"], {"event_id": event_id, "limit": limit, "offset": offset}
    for column in FILTERS:
        if filters.get(column) is not None:
            where.append(f"a.{column} = :{column}")
            params[column] = filters[column]
    sql = f"{SELECT} WHERE {' AND '.join(where)} {ORDER} LIMIT :limit OFFSET :offset"
    return [dict(row) for row in db.execute(text(sql), params).mappings()]


def create_action(db: Session, event_id: int, data: dict, created_by: Optional[int]) -> int:
    """Insert an action and return its id. Does NOT commit."""
    location = data.get("location")
    return db.execute(text(f"""
        INSERT INTO emergency_actions (event_id, title, description, action_type, priority, status,
                                       location, assigned_to, created_by, due_at)
        VALUES (:event_id, :title, :description, :action_type, :priority, :status,
                {POINT}, :assigned_to, :created_by, :due_at)
        RETURNING action_id"""), {
        "event_id": event_id, "title": data["title"], "description": data.get("description"),
        "action_type": data["action_type"], "priority": data["priority"], "status": data["status"],
        "lon": location["longitude"] if location else None,
        "lat": location["latitude"] if location else None,
        "assigned_to": data.get("assigned_to"), "created_by": created_by, "due_at": data.get("due_at"),
    }).scalar_one()


def update_action(db: Session, action_id: int, changes: dict) -> None:
    """Apply the given changes and set updated_at. A 'location' of None clears the pin. Does NOT commit."""
    assignments, params = [], {"id": action_id}
    for column in UPDATABLE:
        if column in changes:
            assignments.append(f"{column} = :{column}")
            params[column] = changes[column]
    if "location" in changes:
        location = changes["location"]
        assignments.append(f"location = {POINT}")
        params["lon"] = location["longitude"] if location else None
        params["lat"] = location["latitude"] if location else None
    assignments.append("updated_at = now()")
    db.execute(text(f"UPDATE emergency_actions SET {', '.join(assignments)} WHERE action_id = :id"), params)


def delete_action(db: Session, action_id: int) -> bool:
    """True if an action was deleted. Does NOT commit."""
    row = db.execute(text("DELETE FROM emergency_actions WHERE action_id = :id RETURNING action_id"),
                     {"id": action_id}).first()
    return row is not None


def locations_geojson(db: Session, event_id: int) -> dict:
    rows = db.execute(text("""
        SELECT a.action_id, a.title, a.action_type, a.priority, a.status,
               ST_X(a.location) AS lon, ST_Y(a.location) AS lat
          FROM emergency_actions a
         WHERE a.event_id = :event_id AND a.location IS NOT NULL
         ORDER BY a.action_id"""), {"event_id": event_id}).mappings()
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
        "properties": {k: row[k] for k in ("action_id", "title", "action_type", "priority", "status")},
    } for row in rows]}
