"""
GeoFlood AI - Phase 29a test: the flood progression endpoint and the 'acquired_at' upload field,
with the REAL access rules (login required).

The progression series in sections 1-3 are SYNTHETIC rows written straight into the test database.
Section 5 uploads the real chip India_591317 twice, with two different dates typed in. The result is
'no change' because it is the same picture - that only checks the plumbing, it is not a flood result.

DESTRUCTIVE: rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m backend.test_progression_api
"""

import os
import tempfile
from pathlib import Path

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
ROLES = {"viewer_x": "viewer", "analyst_x": "analyst"}
PASSWORDS = {name: f"{name}-test-password-1" for name in ROLES}
CHIP = config.IMG_DIR / "India_591317_S1Hand.tif"
TABLES = ("satellite_images", "flood_analysis", "flood_zones")
BOX = (93.40, 26.30, 93.46, 26.35)
OTHER_BOX = (94.40, 27.30, 94.46, 27.35)


def ok(message):
    print(f"  [OK] {message}")


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 29a Progression API Test")
    print(SEP)
    if not CHIP.exists():
        raise SystemExit(f"Needed test file not found: {CHIP}")

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
    demo_event = scalar(cur, "SELECT event_id FROM disaster_events WHERE name = 'DEMO: flood test event'")

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

    def add(event_id, acquired, water, box=BOX, valid=25.0, name="synthetic.tif", status="completed"):
        """One synthetic image + analysis written straight into the test database."""
        image_id = scalar(cur, """
            INSERT INTO satellite_images (event_id, source_id, image_role, file_name, file_path,
                                          width_px, height_px, band_count, crs, footprint, acquired_at)
            VALUES (%s, %s, 'event', %s, 'synthetic/none.tif', 100, 100, 2, 'EPSG:4326',
                    ST_MakeEnvelope(%s, %s, %s, %s, 4326), %s) RETURNING image_id""",
                          (event_id, source_id, name, *box, acquired))
        return scalar(cur, """
            INSERT INTO flood_analysis (image_id, baseline_method, model_name, threshold, status,
                                        valid_area_km2, nodata_area_km2, water_area_km2, water_pct_of_valid,
                                        area_method)
            VALUES (%s, 'none', 'synthetic.pth', 0.5, %s, %s, 0, %s, %s, 'synthetic')
            RETURNING analysis_id""", (image_id, status, valid, water, water / valid * 100))

    with tempfile.TemporaryDirectory() as tmp_name, TestClient(app) as client:
        tmp = Path(tmp_name)
        closed = Settings(public_read=False, uploads_dir=tmp / "uploads", outputs_dir=tmp / "outputs")
        app.dependency_overrides[get_db] = use_test_db
        app.dependency_overrides[get_settings] = lambda: closed

        tokens = {}
        for name in ROLES:
            r = client.post("/api/auth/login", data={"username": name, "password": PASSWORDS[name]})
            assert r.status_code == 200, r.text
            tokens[name] = r.json()["access_token"]

        def call(method, url, who=None, **kwargs):
            headers = {"Authorization": f"Bearer {tokens[who]}"} if who else {}
            return client.request(method, url, headers=headers, **kwargs)

        def new_event(name):
            r = call("POST", "/api/events", "analyst_x", json={"name": name, "country": "India"})
            assert r.status_code == 201, r.text
            return r.json()["event_id"]

        def counts():
            return {t: scalar(cur, f"SELECT count(*) FROM {t}") for t in TABLES}

        # ------------------------------------------------------------ 1
        print("\n--- 1. Access and unknown events ---")
        url = f"/api/events/{demo_event}/progression"
        assert call("GET", url).status_code == 401
        assert call("GET", url, "viewer_x").status_code == 200
        r = call("GET", "/api/events/999999/progression", "viewer_x")
        assert r.status_code == 404, r.text
        assert call("GET", "/api/events/0/progression", "viewer_x").status_code == 422
        ok("no login = 401; a viewer may read; unknown event = 404; id 0 = 422")

        # ------------------------------------------------------------ 2
        print("\n--- 2. An event whose only analysis has no observation date ---")
        r = call("GET", url, "viewer_x")
        body = r.json()
        assert body["event_id"] == demo_event and body["series"] == []
        assert [u["reason"] for u in body["unassigned"]] == ["no_date"]
        assert body["unassigned"][0]["detail"] and "not proof" in body["note"]
        ok("the demo analysis is listed as 'no_date' with an explanation, and no series is invented")

        # ------------------------------------------------------------ 3
        print("\n--- 3. A synthetic series of one area on three dates ---")
        ev = new_event("SYNTHETIC progression event")
        a1 = add(ev, "2026-10-01 06:00+00", 2.5)
        a3 = add(ev, "2026-10-13 06:00+00", 6.8)
        a2 = add(ev, "2026-10-07 06:00+00", 4.2)
        add(ev, None, 9.9, name="undated.tif")
        add(ev, "2026-10-05 06:00+00", 1.0, box=OTHER_BOX, name="elsewhere.tif")
        before = counts()
        r = call("GET", f"/api/events/{ev}/progression", "viewer_x")
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["series"]) == 1
        s = body["series"][0]
        assert [p["analysis_id"] for p in s["points"]] == [a1, a2, a3]
        assert [c["direction"] for c in s["changes"]] == ["more", "more"]
        assert [c["delta_km2"] for c in s["changes"]] == [1.7, 2.6]
        assert s["summary"]["total_delta_km2"] == 4.3 and s["warnings"] == []
        reasons = sorted(u["reason"] for u in body["unassigned"])
        assert reasons == ["no_date", "only_one_date"], reasons
        assert counts() == before, "reading the progression must not change the database"
        ok("3 dated analyses of one area -> 1 series (+1.7, +2.6 km2); undated and other-area ones are explained")
        ok("nothing was written to the database")

        # ------------------------------------------------------------ 4
        print("\n--- 4. 'acquired_at' is checked before any work is done ---")
        ev4 = new_event("Phase 29 date checks")
        before = counts()
        for bad in ("yesterday", "27/10/2026", "1999-01-01", "2999-01-01"):
            r = call("POST", "/api/analyses", "analyst_x",
                     data={"event_id": ev4, "source_id": source_id, "acquired_at": bad},
                     files={"file": (CHIP.name, CHIP.read_bytes(), "image/tiff")})
            assert r.status_code == 422, (bad, r.status_code, r.text)
        assert counts() == before
        ok("'yesterday', '27/10/2026', 1999 and 2999 are all refused with 422; nothing saved")

        # ------------------------------------------------------------ 5
        print("\n--- 5. Real uploads with dates (this runs the model twice) ---")
        ids = {}
        for when, label in (("2026-10-20", "first"), ("2026-10-27T05:30:00Z", "second")):
            r = call("POST", "/api/analyses", "analyst_x",
                     data={"event_id": ev4, "source_id": source_id, "acquired_at": when},
                     files={"file": (CHIP.name, CHIP.read_bytes(), "image/tiff")})
            assert r.status_code == 201, r.text
            ids[label] = r.json()["analysis_id"]
        stored = scalar(cur, "SELECT array_agg(to_char(i.acquired_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') "
                             "ORDER BY a.analysis_id) FROM flood_analysis a JOIN satellite_images i "
                             "ON i.image_id = a.image_id WHERE i.event_id = %s", (ev4,))
        assert stored == ["2026-10-20 00:00", "2026-10-27 05:30"], stored
        ok("the dates typed at upload are stored in satellite_images.acquired_at (UTC)")

        r = call("POST", "/api/analyses", "analyst_x", data={"event_id": ev4, "source_id": source_id},
                 files={"file": (CHIP.name, CHIP.read_bytes(), "image/tiff")})
        assert r.status_code == 201, r.text
        undated_id = r.json()["analysis_id"]
        assert scalar(cur, "SELECT i.acquired_at IS NULL FROM flood_analysis a JOIN satellite_images i "
                           "ON i.image_id = a.image_id WHERE a.analysis_id = %s", (undated_id,))
        ok("an upload with no date still works and keeps acquired_at empty (as before Phase 29)")

        body = call("GET", f"/api/events/{ev4}/progression", "viewer_x").json()
        assert len(body["series"]) == 1
        s = body["series"][0]
        assert [p["analysis_id"] for p in s["points"]] == [ids["first"], ids["second"]]
        assert s["changes"][0]["direction"] == "similar" and s["changes"][0]["delta_km2"] == 0.0
        assert [u["reason"] for u in body["unassigned"]] == ["no_date"]
        ok("same picture on two dates = one series with 'similar' (0.0 km2 change); the undated upload is listed apart")

        # ------------------------------------------------------------ 6
        print("\n--- 6. The viewer still cannot upload ---")
        r = call("POST", "/api/analyses", "viewer_x",
                 data={"event_id": ev4, "source_id": source_id, "acquired_at": "2026-10-20"},
                 files={"file": (CHIP.name, CHIP.read_bytes(), "image/tiff")})
        assert r.status_code == 403, r.status_code
        ok("a viewer uploading with a date = 403")

    app.dependency_overrides.clear()
    conn.close()
    print("\n" + SEP)
    print("  Progression API tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
