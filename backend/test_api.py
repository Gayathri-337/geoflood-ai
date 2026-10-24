"""
GeoFlood AI - Phase 15 test: the API, end to end, against the TEST database.

DESTRUCTIVE like the database tests: rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m backend.test_api
"""

import os

import psycopg2
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai.src import config
from backend.database import get_db
from backend.main import app

DB_DIR = config.ROOT / "database"
SEP = "=" * 70
BUILD_FILES = ("reset.sql", "schema.sql", "impact_analysis.sql", "sample_data.sql")
ORIGIN = "http://localhost:5173"


def ok(message):
    print(f"  [OK] {message}")


def rebuild(cur):
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 15 API Test")
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
    cur.execute("SELECT current_database()")
    db_name = cur.fetchone()[0]
    if "test" not in db_name:
        raise SystemExit(f"Refusing to run: database '{db_name}' does not look like a test database.")
    print(f"\nTest database: {db_name}")
    rebuild(cur)

    engine = create_engine(test_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False)

    def use_test_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = use_test_db
    client = TestClient(app)

    # ---------------------------------------------------------------- 1
    print("\n--- 1. Health checks ---")
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    ok(f"GET /api/health -> {r.json()}")
    r = client.get("/api/health/db")
    j = r.json()
    assert r.status_code == 200 and j["status"] == "ok" and j["missing_tables"] == [], r.text
    assert j["tables_present"] == 13 and j["database"] == db_name
    ok(f"GET /api/health/db -> database '{j['database']}', PostGIS {j['postgis_version'].split()[0]}, "
       f"{j['tables_present']} tables present")

    # ---------------------------------------------------------------- 2
    print("\n--- 2. Reading the sample data ---")
    r = client.get("/api/sources")
    names = {s["name"] for s in r.json()}
    assert r.status_code == 200 and names == {"Sen1Floods11 hand-labeled chips",
                                              "Sentinel-1 (Copernicus Data Space)"}, r.text
    ok("GET /api/sources -> 2 sources")
    r = client.get("/api/events")
    assert r.status_code == 200 and len(r.json()) == 1 and r.json()[0]["name"] == "DEMO: flood test event"
    ok("GET /api/events -> the 1 sample event")

    # ---------------------------------------------------------------- 3
    print("\n--- 3. Creating and reading events ---")
    payload = {"name": "  Test event 1  ", "region_name": "Assam", "country": "India", "status": "active",
               "start_date": "2026-07-01", "end_date": "2026-07-15", "description": "created by test_api.py"}
    r = client.post("/api/events", json=payload)
    assert r.status_code == 201, r.text
    created = r.json()
    assert isinstance(created["event_id"], int) and created["created_at"]
    assert created["name"] == "Test event 1", "surrounding spaces should be stripped"
    ok(f"POST /api/events -> 201, event_id {created['event_id']}, name trimmed, created_at set by the database")

    r = client.get(f"/api/events/{created['event_id']}")
    assert r.status_code == 200 and r.json() == created
    ok("GET /api/events/{id} returns the same data")

    r = client.get("/api/events")
    assert [e["name"] for e in r.json()] == ["Test event 1", "DEMO: flood test event"]
    ok("GET /api/events -> 2 events, newest first")

    cur.execute("SELECT name, status, start_date::text, end_date::text, created_by FROM disaster_events "
                "WHERE event_id = %s", (created["event_id"],))
    row = cur.fetchone()
    assert row == ("Test event 1", "active", "2026-07-01", "2026-07-15", None), row
    ok("independent check in PostgreSQL: the row is stored exactly as sent")

    r = client.post("/api/events", json={"name": "Minimal event"})
    assert r.status_code == 201 and r.json()["status"] == "monitoring" and r.json()["country"] is None
    ok("only a name is required; status defaults to 'monitoring'")

    # ---------------------------------------------------------------- 4
    print("\n--- 4. Bad input is refused before it reaches the database ---")
    bad = {
        "empty body": {},
        "empty name": {"name": ""},
        "name of only spaces": {"name": "   "},
        "name over 150 characters": {"name": "x" * 151},
        "unknown status": {"name": "x", "status": "bogus"},
        "end before start": {"name": "x", "start_date": "2026-02-01", "end_date": "2026-01-01"},
        "invalid date": {"name": "x", "start_date": "not-a-date"},
    }
    for label, body in bad.items():
        r = client.post("/api/events", json=body)
        assert r.status_code == 422, f"{label}: expected 422, got {r.status_code}"
    ok(f"{len(bad)} invalid requests all returned 422")
    cur.execute("SELECT count(*) FROM disaster_events")
    assert cur.fetchone()[0] == 3
    ok("no rows were added by the refused requests (still 3 events)")

    assert client.get("/api/events/999999").status_code == 404
    assert client.get("/api/events/abc").status_code == 422
    assert client.get("/api/events/0").status_code == 422
    assert client.get("/api/events/99999999999999999999").status_code == 422
    ok("unknown id -> 404; bad ids (abc, 0, too large) -> 422")

    # ---------------------------------------------------------------- 5
    print("\n--- 5. Paging ---")
    assert len(client.get("/api/events?limit=1").json()) == 1
    assert client.get("/api/events?limit=1&offset=1").json()[0]["name"] == "Test event 1"
    assert client.get("/api/events?limit=0").status_code == 422
    assert client.get("/api/events?limit=201").status_code == 422
    assert client.get("/api/events?offset=-1").status_code == 422
    ok("limit and offset work; limit 0 or over 200, and a negative offset, are refused")

    # ---------------------------------------------------------------- 6
    print("\n--- 6. Documentation and CORS ---")
    paths = set(client.get("/openapi.json").json()["paths"])
    expected = {"/api/health", "/api/health/db", "/api/sources", "/api/events", "/api/events/{event_id}"}
    assert expected <= paths, paths
    assert client.get("/docs").status_code == 200
    ok("/openapi.json lists all 5 endpoints and /docs loads")

    r = client.get("/api/health", headers={"Origin": ORIGIN})
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    r = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers
    r = client.options("/api/events", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST",
                                               "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 200 and r.headers.get("access-control-allow-origin") == ORIGIN
    ok(f"CORS: {ORIGIN} is allowed (including the preflight request), another origin is not")

    # ---------------------------------------------------------------- 7
    print("\n--- 7. When the database is down ---")
    bad_engine = create_engine("postgresql://geoflood:secretpw123@localhost:1/none",
                               connect_args={"connect_timeout": 2})
    BadSession = sessionmaker(bind=bad_engine)

    def use_bad_db():
        db = BadSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = use_bad_db
    r = client.get("/api/events")
    assert r.status_code == 503, r.status_code
    assert "secretpw123" not in r.text and "localhost" not in r.text and "postgresql" not in r.text
    ok(f"unreachable database -> 503 {r.json()}, and no connection details are leaked")
    app.dependency_overrides[get_db] = use_test_db
    assert client.get("/api/events").status_code == 200
    ok("the API recovers as soon as a working database is available")

    app.dependency_overrides.clear()
    engine.dispose()
    bad_engine.dispose()
    rebuild(cur)
    conn.close()
    print("\n  Test database reset to the sample data.")
    print("\n" + SEP)
    print("  API tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
