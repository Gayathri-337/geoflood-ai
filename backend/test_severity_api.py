"""
GeoFlood AI - Phase 25 test: the severity endpoints, with the REAL access rules (login required).

DESTRUCTIVE: rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m backend.test_severity_api
"""

import json
import os

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
PASSWORDS = {"viewer_s": "viewer-severity-pw-1", "analyst_s": "analyst-severity-pw-1"}
KEYS = {"analysis_id", "level", "driven_by", "impact_included", "stored_severity", "indicators", "note"}


def ok(message):
    print(f"  [OK] {message}")


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def by_key(body):
    return {i["key"]: i for i in body["indicators"]}


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 25 Severity API Test")
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
    aid = scalar(cur, "SELECT analysis_id FROM flood_analysis ORDER BY analysis_id LIMIT 1")

    engine = create_engine(test_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False)

    def use_test_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    db = Session()
    for username, role in (("viewer_s", "viewer"), ("analyst_s", "analyst")):
        user_service.create_user(db, username=username, email=f"{username}@example.com",
                                 password=PASSWORDS[username], role=role)
    db.commit()
    db.close()

    closed = Settings(public_read=False)
    app.dependency_overrides[get_db] = use_test_db
    app.dependency_overrides[get_settings] = lambda: closed
    client = TestClient(app)

    def token(name):
        r = client.post("/api/auth/login", data={"username": name, "password": PASSWORDS[name]})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    viewer, analyst = token("viewer_s"), token("analyst_s")
    url = f"/api/analyses/{aid}/severity"

    # ------------------------------------------------------------ 1
    print("\n--- 1. Before the impact is computed ---")
    r = client.get(url, headers=viewer)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == KEYS
    ind = by_key(body)
    assert body["level"] == "moderate" and body["driven_by"] == ["area_pct"]
    assert body["impact_included"] is False and body["stored_severity"] is None
    assert ind["area_pct"]["value"] == 6.0 and ind["area_pct"]["level"] == "moderate"
    assert all(ind[k]["value"] is None and ind[k]["level"] is None
               for k in ("road_km", "villages", "farmland_km2", "facilities"))
    ok("the sample analysis (6.0% new water) is moderate on the water area alone; impact indicators are empty")

    # ------------------------------------------------------------ 2
    print("\n--- 2. After the impact is computed (the fabricated sample layout) ---")
    assert client.post(f"/api/analyses/{aid}/impact", headers=analyst).status_code == 200
    body = client.get(url, headers=viewer).json()
    ind = by_key(body)
    assert body["impact_included"] is True and body["level"] == "high" and body["driven_by"] == ["facilities"]
    assert 1.545 <= ind["road_km"]["value"] <= 1.555 and ind["road_km"]["level"] == "moderate"
    assert ind["villages"]["value"] == 2 and ind["villages"]["level"] == "moderate"
    assert 0.440 <= ind["farmland_km2"]["value"] <= 0.443 and ind["farmland_km2"]["level"] == "moderate"
    assert ind["facilities"]["value"] == 1 and ind["facilities"]["level"] == "high"
    assert body["stored_severity"] is None
    assert scalar(cur, "SELECT severity FROM flood_analysis WHERE analysis_id = %s", (aid,)) is None
    ok("roads 1.55 km, villages 2, farmland 0.44 km2 are moderate; the hospital inside makes it high, "
       "decided by the facilities; reading saved nothing")

    # ------------------------------------------------------------ 3
    print("\n--- 3. Who may read and who may save ---")
    for method in ("GET", "POST"):
        assert client.request(method, url).status_code == 401
    assert client.post(url, headers=viewer).status_code == 403
    assert client.get(url, headers=viewer).status_code == 200
    ok("anonymous -> 401 for both; a viewer may read but not save (403)")
    r = client.post(url, headers=analyst)
    assert r.status_code == 200 and r.json()["level"] == "high" and r.json()["stored_severity"] == "high"
    assert scalar(cur, "SELECT severity FROM flood_analysis WHERE analysis_id = %s", (aid,)) == "high"
    assert client.get(f"/api/analyses/{aid}", headers=viewer).json()["severity"] == "high"
    ok("an analyst saves it: the database and GET /api/analyses/{id} now say 'high'")

    # ------------------------------------------------------------ 4
    print("\n--- 4. A saved level can become out of date ---")
    cur.execute("UPDATE flood_analysis SET new_flood_pct_of_valid = 30 WHERE analysis_id = %s", (aid,))
    body = client.get(url, headers=viewer).json()
    assert body["level"] == "severe" and body["stored_severity"] == "high" and "area_pct" in body["driven_by"]
    cur.execute("UPDATE flood_analysis SET new_flood_pct_of_valid = 6 WHERE analysis_id = %s", (aid,))
    ok("with 30% new water the live level is severe while the saved one is still high; both are returned")

    # ------------------------------------------------------------ 5
    print("\n--- 5. Roads on bridges do not raise the level ---")
    for name in ("DEMO Road R1", "DEMO Road R3"):
        cur.execute("UPDATE reference_features SET properties = %s::jsonb WHERE name = %s",
                    (json.dumps({"tags": {"bridge": "yes"}}), name))
    ind = by_key(client.get(url, headers=viewer).json())
    assert ind["road_km"]["value"] == 0 and ind["road_km"]["level"] == "low"
    ok("when both affected roads are bridges the flooded road length is 0 and its level is low")

    # ------------------------------------------------------------ 6
    print("\n--- 6. An analysis without a baseline ---")
    cur.execute("UPDATE flood_analysis SET baseline_method = 'none', permanent_water_area_km2 = NULL, "
                "new_flood_area_km2 = NULL, new_flood_pct_of_valid = NULL WHERE analysis_id = %s", (aid,))
    body = client.get(url, headers=viewer).json()
    area = by_key(body)["area_pct"]
    assert area["value"] == 15.596 and "detected water" in area["label"]
    assert body["level"] == "high" and body["impact_included"] is False
    ok("detected water (15.6%) counts instead of new water; no impact for the 'water' class yet, so area only")

    # ------------------------------------------------------------ 7
    print("\n--- 7. Bad requests ---")
    assert client.get("/api/analyses/999999/severity", headers=viewer).status_code == 404
    assert client.post("/api/analyses/999999/severity", headers=analyst).status_code == 404
    for bad in ("0", "abc", "99999999999999999999"):
        assert client.get(f"/api/analyses/{bad}/severity", headers=viewer).status_code == 422, bad
    ok("an unknown analysis -> 404 (also when saving); a bad id -> 422")

    app.dependency_overrides.clear()
    engine.dispose()
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())
    conn.close()
    print("\n  Test database reset to the sample data (the test users are gone).")
    print("\n" + SEP)
    print("  Severity API tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
