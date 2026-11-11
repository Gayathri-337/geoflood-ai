"""
GeoFlood AI - Phase 26a test: emergency actions, with the REAL access rules (login required).

DESTRUCTIVE: rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m backend.test_actions_api
"""

import os
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai.src import config
from backend.config import Settings, get_settings
from backend.database import get_db
from backend.main import app
from backend.services import users as user_service

DB_DIR = config.ROOT / "database"
SEP = "=" * 70
BUILD_FILES = ("reset.sql", "schema.sql", "impact_analysis.sql", "sample_data.sql")
ROLES = {"viewer_x": "viewer", "analyst_x": "analyst", "admin_x": "admin", "gone_x": "analyst"}
PASSWORDS = {name: f"{name}-test-password-1" for name in ROLES}
OUT_KEYS = {"action_id", "event_id", "title", "description", "action_type", "priority", "status", "longitude",
            "latitude", "assigned_to", "assigned_to_username", "created_by", "due_at", "created_at", "updated_at"}
UTC = timezone.utc


def ok(message):
    print(f"  [OK] {message}")


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def parse(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 26a Emergency Actions API Test")
    print(SEP)

    load_dotenv(config.ROOT / ".env")
    test_url, main_url = os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL")
    if not test_url:
        raise SystemExit("TEST_DATABASE_URL is missing from .env.")
    if test_url == main_url:
        raise SystemExit("TEST_DATABASE_URL must differ from DATABASE_URL: this test DROPS all tables.")
    try:
        conn = psycopg2.connect(test_url, connect_timeout=5)
    except psycopg2.OperationalError as err:
        raise SystemExit(f"Could not connect:\n{err}")
    conn.autocommit = True
    cur = conn.cursor()
    db_name = scalar(cur, "SELECT current_database()")
    if "test" not in db_name:
        raise SystemExit(f"Refusing to run: database '{db_name}' does not look like a test database.")
    print(f"\nTest database: {db_name}")
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())
    sample_event = scalar(cur, "SELECT event_id FROM disaster_events ORDER BY event_id LIMIT 1")
    admin_demo = scalar(cur, "SELECT user_id FROM users WHERE username = 'admin_demo'")

    engine = create_engine(test_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False)

    def use_test_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    db = Session()
    for username, role in ROLES.items():
        user_service.create_user(db, username=username, email=f"{username}@example.com",
                                 password=PASSWORDS[username], role=role)
    db.commit()
    db.close()
    cur.execute("UPDATE users SET is_active = false WHERE username = 'gone_x'")
    ids = {name: scalar(cur, "SELECT user_id FROM users WHERE username = %s", (name,)) for name in ROLES}

    closed = Settings(public_read=False)
    app.dependency_overrides[get_db] = use_test_db
    app.dependency_overrides[get_settings] = lambda: closed
    client = TestClient(app)

    tokens = {}
    for name in ("viewer_x", "analyst_x", "admin_x"):
        r = client.post("/api/auth/login", data={"username": name, "password": PASSWORDS[name]})
        assert r.status_code == 200, r.text
        tokens[name] = r.json()["access_token"]

    def call(method, url, who=None, **kwargs):
        headers = {"Authorization": f"Bearer {tokens[who]}"} if who else {}
        return client.request(method, url, headers=headers, **kwargs)

    def actions_url(event_id):
        return f"/api/events/{event_id}/actions"

    def n_actions():
        return scalar(cur, "SELECT count(*) FROM emergency_actions")

    def new_event(name):
        cur.execute("INSERT INTO disaster_events (name) VALUES (%s) RETURNING event_id", (name,))
        return cur.fetchone()[0]

    base = {"title": "Valid title", "action_type": "other"}

    # ------------------------------------------------------------ 1
    print("\n--- 1. Listing the two sample actions ---")
    r = call("GET", actions_url(sample_event), "viewer_x")
    assert r.status_code == 200, r.text
    shelter, road = r.json()
    assert shelter["title"].startswith("DEMO: open relief shelter") and shelter["priority"] == "high"
    assert road["title"].startswith("DEMO: close road R1") and road["status"] == "in_progress"
    assert set(shelter) == OUT_KEYS
    assert (shelter["longitude"], shelter["latitude"]) == (92.935, 26.605)
    assert shelter["assigned_to_username"] == "analyst_demo" and shelter["created_by"] == admin_demo
    ok("a viewer sees both, the high-priority shelter first; location, assignee name and creator are right")

    # ------------------------------------------------------------ 2
    print("\n--- 2. Filters and paging ---")
    url = actions_url(sample_event)
    assert [a["status"] for a in call("GET", f"{url}?status=in_progress", "viewer_x").json()] == ["in_progress"]
    assert [a["priority"] for a in call("GET", f"{url}?priority=high", "viewer_x").json()] == ["high"]
    assert [a["action_type"] for a in call("GET", f"{url}?action_type=shelter", "viewer_x").json()] == ["shelter"]
    assert call("GET", f"{url}?status=planned&priority=medium", "viewer_x").json() == []
    assert len(call("GET", f"{url}?limit=1", "viewer_x").json()) == 1
    assert call("GET", f"{url}?limit=1&offset=1", "viewer_x").json()[0]["action_id"] == road["action_id"]
    for bad in ("status=done", "priority=urgent", "action_type=teleport", "limit=0", "limit=501", "offset=-1"):
        assert call("GET", f"{url}?{bad}", "viewer_x").status_code == 422, bad
    ok("status, priority and type filters work and combine; paging works; bad filter values -> 422")

    # ------------------------------------------------------------ 3
    print("\n--- 3. Creating actions (as an analyst) ---")
    payload = {"title": "  Evacuate Village Alpha  ", "description": "Move families to the school.",
               "action_type": "evacuation", "priority": "critical",
               "location": {"longitude": 92.925, "latitude": 26.595},
               "assigned_to": ids["analyst_x"], "due_at": "2026-11-20T09:00:00"}
    r = call("POST", actions_url(sample_event), "analyst_x", json=payload)
    assert r.status_code == 201, r.text
    a = r.json()
    assert set(a) == OUT_KEYS and a["title"] == "Evacuate Village Alpha" and a["status"] == "planned"
    assert a["event_id"] == sample_event and a["created_by"] == ids["analyst_x"]
    assert a["assigned_to_username"] == "analyst_x" and (a["longitude"], a["latitude"]) == (92.925, 26.595)
    assert parse(a["due_at"]) == datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
    cur.execute("SELECT ST_X(location), ST_Y(location), created_by FROM emergency_actions WHERE action_id = %s",
                (a["action_id"],))
    assert cur.fetchone() == (92.925, 26.595, ids["analyst_x"])
    ok("created: title trimmed, status defaults to 'planned', the creator is the logged-in analyst, the time "
       "without a zone is read as UTC, and the pin is stored as a PostGIS point")

    r = call("POST", actions_url(sample_event), "analyst_x", json={**base, "due_at": "2026-11-20T09:00:00+05:30"})
    assert r.status_code == 201
    minimal = r.json()
    assert parse(minimal["due_at"]) == datetime(2026, 11, 20, 3, 30, tzinfo=UTC)
    assert minimal["priority"] == "medium" and minimal["location"] if "location" in minimal else True
    assert minimal["longitude"] is None and minimal["assigned_to"] is None and minimal["description"] is None
    ok("only a title and a type are required; a time with +05:30 is the same moment as 03:30 UTC")

    # ------------------------------------------------------------ 4
    print("\n--- 4. Bad requests are refused and nothing is stored ---")
    bad_cases = {
        "an empty title": {**base, "title": ""},
        "a title of only spaces": {**base, "title": "   "},
        "a title over 200 characters": {**base, "title": "x" * 201},
        "an unknown action type": {**base, "action_type": "teleport"},
        "no action type": {"title": "Valid title"},
        "an unknown priority": {**base, "priority": "urgent"},
        "an unknown status": {**base, "status": "done"},
        "latitude over 90": {**base, "location": {"longitude": 92.9, "latitude": 91}},
        "longitude over 180": {**base, "location": {"longitude": 181, "latitude": 26.5}},
        "a location missing a coordinate": {**base, "location": {"longitude": 92.9}},
        "a description over 5000 characters": {**base, "description": "x" * 5001},
        "assigned_to 0": {**base, "assigned_to": 0},
        "a due time that is not a time": {**base, "due_at": "next week"},
    }
    before = n_actions()
    for label, body in bad_cases.items():
        r = call("POST", actions_url(sample_event), "analyst_x", json=body)
        assert r.status_code == 422, (label, r.status_code, r.text[:200])
    assert n_actions() == before
    ok(f"{len(bad_cases)} invalid requests all -> 422; the table still has {before} rows")
    for who_url in (actions_url(999999), actions_url(999999) + "/geojson"):
        assert call("GET", who_url, "viewer_x").status_code == 404
    assert call("POST", actions_url(999999), "analyst_x", json=base).status_code == 404
    ok("an unknown event -> 404 for listing, map points and creating")
    for label, assignee in (("an unknown person", 999999), ("a disabled person", ids["gone_x"])):
        r = call("POST", actions_url(sample_event), "analyst_x", json={**base, "assigned_to": assignee})
        assert r.status_code == 422 and "does not exist or is disabled" in r.json()["detail"], label
    assert n_actions() == before
    ok("assigning to an unknown or a disabled person -> 422")

    # ------------------------------------------------------------ 5
    print("\n--- 5. Who may do what ---")
    target = f"/api/actions/{a['action_id']}"
    probes = [("GET", actions_url(sample_event), {}), ("GET", actions_url(sample_event) + "/geojson", {}),
              ("POST", actions_url(sample_event), {"json": base}),
              ("PATCH", target, {"json": {"status": "completed"}}), ("DELETE", target, {})]
    for method, url, kwargs in probes:
        assert call(method, url, None, **kwargs).status_code == 401, (method, url)
    ok("anonymous -> 401 on all five endpoints")
    for method, url, kwargs in probes[:2]:
        assert call(method, url, "viewer_x", **kwargs).status_code == 200
    for method, url, kwargs in probes[2:]:
        assert call(method, url, "viewer_x", **kwargs).status_code == 403, (method, url)
    ok("a viewer may read (200) but not create, change or delete (403)")
    r = call("DELETE", target, "analyst_x")
    assert r.status_code == 403 and "admin" in r.json()["detail"]
    assert scalar(cur, "SELECT status FROM emergency_actions WHERE action_id = %s", (a["action_id"],)) == "planned"
    ok("an analyst may not delete (403, admins only) and the action is untouched")

    # ------------------------------------------------------------ 6
    print("\n--- 6. Changing an action ---")
    created_at, before_update = parse(a["created_at"]), parse(a["updated_at"])
    r = call("PATCH", target, "analyst_x", json={"status": "in_progress", "priority": "high", "title": " New title "})
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["status"], b["priority"], b["title"]) == ("in_progress", "high", "New title")
    assert b["description"] == a["description"] and b["longitude"] == a["longitude"]
    assert parse(b["created_at"]) == created_at and parse(b["updated_at"]) > before_update
    ok("only the sent fields change; created_at stays; updated_at moves forward")

    r = call("PATCH", target, "analyst_x", json={"location": None, "description": None, "due_at": None,
                                                 "assigned_to": None})
    c = r.json()
    assert (c["longitude"], c["latitude"], c["description"], c["due_at"]) == (None, None, None, None)
    assert c["assigned_to"] is None and c["assigned_to_username"] is None
    assert scalar(cur, "SELECT location IS NULL FROM emergency_actions WHERE action_id = %s", (a["action_id"],))
    ok("null clears the pin, the description, the due time and the assignee")

    r = call("PATCH", target, "analyst_x", json={"location": {"longitude": 93.1, "latitude": 26.7},
                                                 "assigned_to": ids["admin_x"], "status": "completed"})
    d = r.json()
    assert (d["longitude"], d["latitude"], d["assigned_to_username"], d["status"]) == (93.1, 26.7, "admin_x", "completed")
    ok("a pin can be set again, the action can be assigned to someone else, and completed")

    for label, body in {"a null title": {"title": None}, "a null status": {"status": None},
                        "an empty body": {}, "an unknown status": {"status": "done"},
                        "a bad pin": {"location": {"longitude": 500, "latitude": 0}},
                        "a disabled assignee": {"assigned_to": ids["gone_x"]}}.items():
        r = call("PATCH", target, "analyst_x", json=body)
        assert r.status_code == 422, (label, r.status_code, r.text[:200])
    assert call("PATCH", "/api/actions/999999", "analyst_x", json={"status": "planned"}).status_code == 404
    assert call("PATCH", "/api/actions/0", "analyst_x", json={"status": "planned"}).status_code == 422
    assert call("GET", target, "viewer_x").status_code in (404, 405)       # there is no single-action GET
    ok("null for a required field, an empty body, a bad status, a bad pin and a disabled assignee -> 422; "
       "an unknown action -> 404; id 0 -> 422")

    # ------------------------------------------------------------ 7
    print("\n--- 7. Sort order: open first, then priority, then due time ---")
    order_event = new_event("Ordering test")
    specs = [("Low planned", "low", "planned", None),
             ("Critical planned", "critical", "planned", None),
             ("Critical done", "critical", "completed", None),
             ("High in progress, due later", "high", "in_progress", "2026-12-31T10:00:00+00:00"),
             ("High planned, due sooner", "high", "planned", "2026-12-01T10:00:00+00:00")]
    for title, priority, status, due in specs:
        r = call("POST", actions_url(order_event), "analyst_x", json={
            "title": title, "action_type": "rescue", "priority": priority, "status": status, "due_at": due})
        assert r.status_code == 201, r.text
    titles = [x["title"] for x in call("GET", actions_url(order_event), "viewer_x").json()]
    assert titles == ["Critical planned", "High planned, due sooner", "High in progress, due later",
                      "Low planned", "Critical done"], titles
    ok("critical planned, high (sooner due first), low, and the completed one last")

    # ------------------------------------------------------------ 8
    print("\n--- 8. Map points ---")
    map_event = new_event("Map test")
    for title, pin in (("Pinned one", {"longitude": 92.9, "latitude": 26.5}),
                       ("Pinned two", {"longitude": 93.0, "latitude": 26.6}), ("No pin", None)):
        assert call("POST", actions_url(map_event), "analyst_x",
                    json={"title": title, "action_type": "shelter", "location": pin}).status_code == 201
    r = call("GET", actions_url(map_event) + "/geojson", "viewer_x")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 2
    first = fc["features"][0]
    assert first["geometry"] == {"type": "Point", "coordinates": [92.9, 26.5]}
    assert set(first["properties"]) == {"action_id", "title", "action_type", "priority", "status"}
    call("PATCH", f"/api/actions/{first['properties']['action_id']}", "analyst_x", json={"location": None})
    assert len(call("GET", actions_url(map_event) + "/geojson", "viewer_x").json()["features"]) == 1
    ok("only actions with a pin appear, as [longitude, latitude] points; clearing a pin removes it from the map")

    # ------------------------------------------------------------ 9
    print("\n--- 9. Deleting (admins only) ---")
    before = n_actions()
    assert call("DELETE", target, "admin_x").status_code == 204
    assert n_actions() == before - 1
    assert call("DELETE", target, "admin_x").status_code == 404
    assert all(x["action_id"] != a["action_id"] for x in call("GET", actions_url(sample_event), "viewer_x").json())
    ok("an admin deletes it (204); it is gone from the list; deleting it again -> 404")

    app.dependency_overrides.clear()
    engine.dispose()
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())
    conn.close()
    print("\n  Test database reset to the sample data (the test users are gone).")
    print("\n" + SEP)
    print("  Emergency actions API tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
