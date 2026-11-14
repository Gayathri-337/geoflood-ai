"""
GeoFlood AI - Phase 30 test: the reference-coverage endpoint, with the REAL access rules (login required).

The features and images below are SYNTHETIC rows placed far away from the sample data (longitudes 150-170), so
they only affect this test.

DESTRUCTIVE: rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m backend.test_coverage_api
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


def ok(message):
    print(f"  [OK] {message}")


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 30 Reference Coverage API Test")
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

    def add_analysis(west, south):
        """A synthetic image (0.05 degrees square) with one analysis; returns the analysis id."""
        image_id = scalar(cur, """
            INSERT INTO satellite_images (event_id, source_id, image_role, file_name, file_path, width_px, height_px,
                                          band_count, crs, footprint)
            VALUES (%s, %s, 'event', 'synthetic.tif', 'synthetic/none.tif', 100, 100, 2, 'EPSG:4326',
                    ST_MakeEnvelope(%s, %s, %s, %s, 4326)) RETURNING image_id""",
                          (event_id, source_id, west, south, west + 0.05, south + 0.05))
        return scalar(cur, """
            INSERT INTO flood_analysis (image_id, baseline_method, model_name, threshold, status, valid_area_km2,
                                        nodata_area_km2, water_area_km2, water_pct_of_valid, area_method)
            VALUES (%s, 'none', 'synthetic.pth', 0.5, 'completed', 25, 0, 2.5, 10, 'synthetic')
            RETURNING analysis_id""", (image_id,))

    def add_feature(layer, ref, wkt):
        cur.execute("INSERT INTO reference_features (layer, name, category, source, source_ref, geom) "
                    "VALUES (%s, %s, 'synthetic', 'test', %s, ST_GeomFromText(%s, 4326))", (layer, ref, ref, wkt))

    # A: a village, two roads and a facility, but no farmland
    a_partial = add_analysis(150.0, 10.0)
    add_feature("village", "a-village", "POINT(150.01 10.01)")
    add_feature("road", "a-road-1", "LINESTRING(150.01 10.02, 150.04 10.02)")
    add_feature("road", "a-road-2", "LINESTRING(150.01 10.03, 150.04 10.03)")
    add_feature("infrastructure", "a-clinic", "POINT(150.02 10.02)")
    # a feature just OUTSIDE image A must not be counted
    add_feature("farmland", "a-farm-outside", "POLYGON((150.2 10.2, 150.3 10.2, 150.3 10.3, 150.2 10.3, 150.2 10.2))")
    # B: nothing at all
    a_none = add_analysis(160.0, 20.0)
    # C: every layer has something
    a_ok = add_analysis(170.0, 30.0)
    add_feature("village", "c-village", "POINT(170.01 30.01)")
    add_feature("road", "c-road", "LINESTRING(170.01 30.02, 170.04 30.02)")
    add_feature("farmland", "c-farm", "POLYGON((170.01 30.01, 170.02 30.01, 170.02 30.02, 170.01 30.02, 170.01 30.01))")
    add_feature("infrastructure", "c-school", "POINT(170.03 30.03)")

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
    token = r.json()["access_token"]

    def get(url, login=True):
        return client.get(url, headers={"Authorization": f"Bearer {token}"} if login else {})

    print("\n--- 1. Access and wrong requests ---")
    assert get(f"/api/analyses/{a_ok}/reference-coverage", login=False).status_code == 401
    assert get(f"/api/analyses/{a_ok}/reference-coverage").status_code == 200
    assert get("/api/analyses/999999/reference-coverage").status_code == 404
    assert get("/api/analyses/0/reference-coverage").status_code == 422
    ok("no login = 401; a viewer may read; unknown analysis = 404; id 0 = 422")

    print("\n--- 2. Some layers empty ---")
    body = get(f"/api/analyses/{a_partial}/reference-coverage").json()
    assert body["analysis_id"] == a_partial and body["level"] == "partial"
    assert body["counts"] == {"villages": 1, "roads": 2, "farmland": 0, "infrastructure": 1}, body["counts"]
    assert body["empty_layers"] == ["farmland"] and "no farmland inside this image" in body["message"]
    ok("1 village, 2 roads, 1 facility counted; the farmland outside the image is not counted; level 'partial'")

    print("\n--- 3. Nothing at all ---")
    body = get(f"/api/analyses/{a_none}/reference-coverage").json()
    assert body["level"] == "none" and sum(body["counts"].values()) == 0
    assert "no data for this area" in body["message"]
    ok("level 'none' with the 'no data, not no impact' message")

    print("\n--- 4. Every layer has data ---")
    body = get(f"/api/analyses/{a_ok}/reference-coverage").json()
    assert body["level"] == "ok" and body["counts"] == {"villages": 1, "roads": 1, "farmland": 1, "infrastructure": 1}
    ok("level 'ok' with one feature in each layer")

    print("\n--- 5. Reading changes nothing ---")
    before = scalar(cur, "SELECT count(*) FROM reference_features")
    for analysis in (a_partial, a_none, a_ok):
        get(f"/api/analyses/{analysis}/reference-coverage")
    assert scalar(cur, "SELECT count(*) FROM reference_features") == before
    assert scalar(cur, "SELECT count(*) FROM affected_roads") == 0
    ok("no reference feature or impact row was added, changed or removed")

    print("\n--- 6. The PDF report still downloads for an image with no reference data ---")
    r = get(f"/api/analyses/{a_none}/report.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF-")
    ok("report.pdf = 200 for the analysis without reference data")

    app.dependency_overrides.clear()
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())
    conn.close()
    print("\n  Test database reset to the sample data.")
    print("\n" + SEP)
    print("  Reference coverage API tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
