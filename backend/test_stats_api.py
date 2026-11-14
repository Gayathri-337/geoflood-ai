"""
GeoFlood AI - Phase 31 test: the dashboard statistics (repeat count and severity overview), with the REAL access
rules (login required). The extra analyses are SYNTHETIC rows written straight into the test database.

DESTRUCTIVE: rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m backend.test_stats_api
"""

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
ROLES = {"viewer_x": "viewer"}
PASSWORDS = {name: f"{name}-test-password-1" for name in ROLES}
SHA = "a" * 64


def ok(message):
    print(f"  [OK] {message}")


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 31 Dashboard Statistics Test")
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
    source_id = scalar(cur, "SELECT source_id FROM satellite_sources ORDER BY source_id LIMIT 1")
    event_id = scalar(cur, "SELECT event_id FROM disaster_events ORDER BY event_id LIMIT 1")

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

    app.dependency_overrides[get_db] = use_test_db
    app.dependency_overrides[get_settings] = lambda: Settings(public_read=False)
    client = TestClient(app)
    r = client.post("/api/auth/login", data={"username": "viewer_x", "password": PASSWORDS["viewer_x"]})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    def stats():
        r = client.get("/api/stats/dashboard", headers=headers)
        assert r.status_code == 200, r.text
        return r.json()

    def add_run(sha, baseline, status="completed", severity=None):
        """One synthetic image (a new image row, like every real upload) with one analysis."""
        image_id = scalar(cur, """
            INSERT INTO satellite_images (event_id, source_id, image_role, file_name, file_path, file_sha256,
                                          width_px, height_px, band_count, crs, footprint)
            VALUES (%s, %s, 'event', 'synthetic.tif', 'synthetic/none.tif', %s, 100, 100, 2, 'EPSG:4326',
                    ST_MakeEnvelope(150, 10, 150.05, 10.05, 4326)) RETURNING image_id""", (event_id, source_id, sha))
        permanent, new = (None, None) if baseline == "none" else (1.5, 1.0)
        return scalar(cur, """
            INSERT INTO flood_analysis (image_id, baseline_method, model_name, threshold, status, valid_area_km2,
                                        nodata_area_km2, water_area_km2, water_pct_of_valid, permanent_water_area_km2,
                                        new_flood_area_km2, area_method, severity)
            VALUES (%s, %s, 'synthetic.pth', 0.5, %s, 25, 0, 2.5, 10, %s, %s, 'synthetic', %s)
            RETURNING analysis_id""", (image_id, baseline, status, permanent, new, severity))

    print("\n--- 1. Access ---")
    assert client.get("/api/stats/dashboard").status_code == 401
    assert client.get("/api/stats/dashboard", headers=headers).status_code == 200
    ok("no login = 401; a viewer may read")

    print("\n--- 2. The sample data: nothing repeats ---")
    d = stats()
    assert d["analyses_completed"] == 1 and d["repeat_analyses"] == 0, d
    assert sum(d["severity_counts"].values()) == d["analyses_completed"]
    assert set(d["severity_counts"]) == {"low", "moderate", "high", "severe", "not_classified"}
    ok("1 analysis, 0 repeats; the severity counts add up to the completed analyses")

    print("\n--- 3. The same file uploaded again ---")
    add_run(SHA, "none", severity="severe")
    add_run(SHA, "none", severity="high")          # a new image row with the same file: a repeat
    third = add_run(SHA, "jrc")                              # same file but with a baseline: a different analysis
    add_run(SHA, "none")                            # one more repeat
    add_run(SHA, "none", status="failed")                    # failed runs are not counted at all
    d = stats()
    assert d["analyses_completed"] == 5, d["analyses_completed"]
    assert d["repeat_analyses"] == 2, d["repeat_analyses"]   # 5 completed - 3 distinct (sample, file+none, file+jrc)
    ok("5 completed analyses = 3 different runs + 2 repeats; the failed run is ignored")

    print("\n--- 4. The saved severity levels ---")
    assert d["severity_counts"] == {"low": 0, "moderate": 0, "high": 1, "severe": 1, "not_classified": 3}, d["severity_counts"]
    cur.execute("UPDATE flood_analysis SET severity = 'low' WHERE analysis_id = %s", (third,))
    d = stats()
    assert d["severity_counts"]["low"] == 1 and d["severity_counts"]["not_classified"] == 2
    assert sum(d["severity_counts"].values()) == d["analyses_completed"]
    ok("severe 1, high 1, low 1 and 2 not classified; the counts always add up")

    print("\n--- 5. The old totals are unchanged ---")
    total_water = float(scalar(cur, "SELECT sum(water_area_km2) FROM flood_analysis WHERE status = 'completed'"))
    assert abs(d["total_water_area_km2"] - total_water) < 1e-4

    assert d["analyses_with_baseline"] == 2 and "counted twice" in d["note"]
    ok("the totals still add every completed analysis (repeats included), as the note says")

    print("\n--- 6. Reading changes nothing ---")
    before = (scalar(cur, "SELECT count(*) FROM flood_analysis"), scalar(cur, "SELECT count(*) FROM satellite_images"))
    stats()
    assert before == (scalar(cur, "SELECT count(*) FROM flood_analysis"), scalar(cur, "SELECT count(*) FROM satellite_images"))
    ok("no row added or removed")

    app.dependency_overrides.clear()
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())
    conn.close()
    print("\n  Test database reset to the sample data.")
    print("\n" + SEP)
    print("  Dashboard statistics tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
