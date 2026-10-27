"""
GeoFlood AI - Phase 17a test: analyses stored in PostgreSQL and served as GIS data.

Expected numbers for India_591317 come from earlier phases:
  Phase 9/12:  120653 water pixels, 10.74337 km2, 46.022 %, confidence 0.9686
  Phase 11:    47 polygons; the largest has 113704 pixels and mean probability 0.9784
  Phase 12 with the JRC baseline: permanent 6.874565 km2, new 3.868805 km2, 16.573 %, 36.011 %

DESTRUCTIVE: rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m backend.test_analyses_api
"""

import hashlib
import os
import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import psycopg2
import rasterio
from affine import Affine
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from shapely.geometry import shape
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai.src import config
from backend.config import Settings, get_settings
from backend.database import get_db
from backend.main import app
from backend.services.inference import ModelService
from gis.area_calculator import polygon_area_km2

DB_DIR = config.ROOT / "database"
SEP = "=" * 70
BUILD_FILES = ("reset.sql", "schema.sql", "impact_analysis.sql", "seed_sources.sql")
CHIP = config.IMG_DIR / "India_591317_S1Hand.tif"
JRC = config.RAW_DIR / "JRCWaterHand" / "India_591317_JRCWaterHand.tif"


def ok(message):
    print(f"  [OK] {message}")


def rebuild(cur, files=BUILD_FILES):
    for name in files:
        cur.execute((DB_DIR / name).read_text())


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def db_counts(cur):
    return tuple(scalar(cur, f"SELECT count(*) FROM {t}")
                 for t in ("satellite_images", "flood_analysis", "flood_zones"))


def snapshot(tmp):
    return tuple(sorted(p.name for p in (tmp / d).glob("*")) for d in ("uploads", "outputs"))


def write_tif(path, array, crs, transform, dtype="uint8"):
    with rasterio.open(path, "w", driver="GTiff", height=array.shape[1], width=array.shape[2],
                       count=array.shape[0], dtype=dtype, crs=crs, transform=transform) as dst:
        dst.write(array.astype(dtype))
    return path.read_bytes()


def post(client, fields, image=None, baseline=None):
    """image and baseline are (file name, bytes) pairs."""
    image = image or (CHIP.name, CHIP.read_bytes())
    files = {"file": (image[0], image[1], "image/tiff")}
    if baseline is not None:
        files["baseline_file"] = (baseline[0], baseline[1], "image/tiff")
    return client.post("/api/analyses", data=fields, files=files)


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 17a Analyses API Test")
    print(SEP)
    for p in (CHIP, JRC):
        if not p.exists():
            raise SystemExit(f"Needed test file not found: {p}")

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
    rebuild(cur)

    engine = create_engine(test_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False)

    def use_test_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    with rasterio.open(CHIP) as src:
        crs, transform, H, W = src.crs, src.transform, src.height, src.width
        chip_bounds = [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]
    chip_bytes, jrc_bytes = CHIP.read_bytes(), JRC.read_bytes()

    app.dependency_overrides[get_db] = use_test_db
    with tempfile.TemporaryDirectory() as tmp_name, TestClient(app) as client:
        tmp = Path(tmp_name)
        settings = Settings(uploads_dir=tmp / "uploads", outputs_dir=tmp / "outputs")
        app.dependency_overrides[get_settings] = lambda: settings

        # ------------------------------------------------------------ 1
        print("\n--- 1. Setup through the API: an event and the imagery source ---")
        r = client.post("/api/events", json={"name": "Phase 17 test event", "country": "India"})
        assert r.status_code == 201, r.text
        event_id = r.json()["event_id"]
        sources = {s["name"]: s["source_id"] for s in client.get("/api/sources").json()}
        source_id = sources["Sen1Floods11 hand-labeled chips"]
        fields = {"event_id": str(event_id), "source_id": str(source_id)}
        ok(f"event {event_id} created; source id {source_id} = Sen1Floods11 hand-labeled chips")

        # ------------------------------------------------------------ 2
        print("\n--- 2. Analysis WITHOUT a baseline (India_591317) ---")
        r = post(client, fields)
        assert r.status_code == 201, r.text
        a1 = r.json()
        assert a1["status"] == "completed" and a1["baseline_method"] == "none"
        assert a1["event_id"] == event_id and a1["source_id"] == source_id
        assert a1["original_filename"] == CHIP.name and a1["crs"] == "EPSG:4326"
        assert (a1["height_px"], a1["width_px"]) == (512, 512) and a1["warnings"] == []
        assert a1["water_pixels"] == 120653 or abs(a1["water_pixels"] - 120653) <= 240
        assert abs(a1["water_area_km2"] - 10.74337) < 0.0001
        assert abs(a1["valid_area_km2"] - 23.343952) < 0.0001
        assert abs(a1["water_pct_of_valid"] - 46.022) < 0.01
        assert abs(a1["mean_confidence"] - 0.9686) < 0.0005
        assert a1["permanent_water_area_km2"] is None and a1["new_flood_area_km2"] is None
        assert a1["new_flood_share_of_water_pct"] is None and a1["severity"] is None
        assert all(abs(x - y) < 1e-5 for x, y in zip(a1["bounds_wgs84"], chip_bounds))
        assert a1["zone_count"] == 47, a1["zone_count"]
        assert "surface water" in a1["detects"]
        ok(f"201 Created, analysis {a1['analysis_id']}: {a1['water_pixels']:,} water pixels, "
           f"{a1['water_area_km2']:.4f} km2, {a1['water_pct_of_valid']}% (Phase 9/12 values)")
        ok("no baseline -> permanent and new-flood fields are None; 47 zone polygons (as in Phase 11)")

        # ------------------------------------------------------------ 3
        print("\n--- 3. What was written to PostgreSQL (checked with a separate connection) ---")
        cur.execute("""SELECT i.event_id, i.source_id, i.image_role, i.file_name, i.file_path, i.file_sha256,
                              i.width_px, i.height_px, i.band_count, i.crs,
                              ST_XMin(i.footprint), ST_YMin(i.footprint), ST_XMax(i.footprint), ST_YMax(i.footprint),
                              a.baseline_method, a.status, a.water_area_km2, a.mask_path
                         FROM flood_analysis a JOIN satellite_images i ON i.image_id = a.image_id
                        WHERE a.analysis_id = %s""", (a1["analysis_id"],))
        (ev, src_id, role, fname, fpath, sha, w, h, bands, crs_text, x0, y0, x1, y1,
         method, status, water_db, mask_path) = cur.fetchone()
        assert (ev, src_id, role, fname) == (event_id, source_id, "event", CHIP.name)
        assert sha == hashlib.sha256(chip_bytes).hexdigest() and Path(fpath).is_file()
        assert (w, h, bands, crs_text) == (512, 512, 2, "EPSG:4326")
        assert all(abs(a - b) < 1e-5 for a, b in zip((x0, y0, x1, y1), chip_bounds))
        assert (method, status) == ("none", "completed") and abs(float(water_db) - 10.74337) < 0.0001
        assert Path(mask_path).is_file()
        ok("image row: event, source, role, sha256 of the upload, size, bands, CRS and footprint are correct")
        ok("analysis row matches the response; the stored upload and mask files exist")

        cur.execute("SELECT zone_type, count(*) FROM flood_zones WHERE analysis_id = %s GROUP BY zone_type",
                    (a1["analysis_id"],))
        assert dict(cur.fetchall()) == {"water": 47}
        ok("flood_zones: 47 rows, all of class 'water'")

        # ------------------------------------------------------------ 4
        print("\n--- 4. The zones as GeoJSON ---")
        r = client.get(a1["zones_url"])
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
        fc = r.json()
        feats = fc["features"]
        assert fc["type"] == "FeatureCollection" and len(feats) == 47 == a1["zone_count"]
        assert {f["geometry"]["type"] for f in feats} == {"MultiPolygon"}
        assert {f["properties"]["zone_type"] for f in feats} == {"water"}
        biggest = next(f for f in feats if f["properties"]["poly_no"] == 1)
        assert biggest["properties"]["n_pixels"] == 113704
        assert abs(biggest["properties"]["mean_confidence"] - 0.9784) < 0.0006
        ok("FeatureCollection with 47 MultiPolygon features; polygon 1 has 113,704 pixels "
           "and confidence 0.9784 (Phase 11 values)")

        west, south, east, north = a1["bounds_wgs84"]
        for f in feats:
            bx0, by0, bx1, by1 = shape(f["geometry"]).bounds
            assert west - 1e-4 <= bx0 and bx1 <= east + 1e-4 and south - 1e-4 <= by0 and by1 <= north + 1e-4
        ok("every polygon lies inside the image footprint (georeferencing)")

        stored_km2 = sum(f["properties"]["area_km2"] for f in feats)
        utm_km2 = polygon_area_km2(gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326"))
        assert abs(stored_km2 - utm_km2) / utm_km2 < 0.005, (stored_km2, utm_km2)
        assert abs(stored_km2 - a1["water_area_km2"]) / a1["water_area_km2"] < 0.02
        ok(f"polygon area: {stored_km2:.4f} km2 stored by PostGIS, {utm_km2:.4f} km2 by GeoPandas/UTM, "
           f"{a1['water_area_km2']:.4f} km2 counted from raster pixels")
        assert client.get(f"/api/analyses/{a1['analysis_id']}/zones?zone_type=new_flood").json()["features"] == []
        assert client.get(f"/api/analyses/{a1['analysis_id']}/zones?zone_type=bogus").status_code == 422
        assert client.get("/api/analyses/999999/zones").status_code == 404
        ok("zone_type filter works (no new_flood zones here); a bad filter gives 422; unknown analysis gives 404")

        # ------------------------------------------------------------ 5
        print("\n--- 5. Analysis WITH the JRC baseline (permanent water vs new flood) ---")
        r = post(client, fields, baseline=(JRC.name, jrc_bytes))
        assert r.status_code == 201, r.text
        a2 = r.json()
        assert a2["baseline_method"] == "jrc"
        assert abs(a2["water_area_km2"] - 10.74337) < 0.0001
        assert abs(a2["permanent_water_area_km2"] - 6.874565) < 0.0002
        assert abs(a2["new_flood_area_km2"] - 3.868805) < 0.0002
        assert abs(a2["new_flood_pct_of_valid"] - 16.573) < 0.01
        assert abs(a2["new_flood_share_of_water_pct"] - 36.011) < 0.02
        assert abs(a2["permanent_water_area_km2"] + a2["new_flood_area_km2"] - a2["water_area_km2"]) < 1e-4
        ok(f"water {a2['water_area_km2']:.4f} = permanent {a2['permanent_water_area_km2']:.4f} + "
           f"new {a2['new_flood_area_km2']:.4f} km2 ({a2['new_flood_share_of_water_pct']}% new) "
           "- the Phase 12 split")

        z = client.get(a2["zones_url"]).json()["features"]
        by_type = {}
        for f in z:
            by_type.setdefault(f["properties"]["zone_type"], []).append(f["properties"])
        assert set(by_type) == {"permanent_water", "new_flood"} and len(z) == a2["zone_count"]
        assert sum(p["n_pixels"] for ps in by_type.values() for p in ps) <= a2["water_pixels"]
        for zone_type, area in (("permanent_water", a2["permanent_water_area_km2"]),
                                ("new_flood", a2["new_flood_area_km2"])):
            zone_km2 = sum(p["area_km2"] for p in by_type[zone_type])
            assert 0.80 <= zone_km2 / area <= 1.02, (zone_type, zone_km2, area)
            print(f"       {zone_type:<16}{len(by_type[zone_type]):>4} polygons, {zone_km2:.4f} km2 "
                  f"(raster {area:.4f} km2, ratio {zone_km2 / area:.3f})")
        ok("zones are split into permanent_water and new_flood; polygon areas follow the raster areas "
           "(small blobs are cleaned away)")
        only_new = client.get(f"/api/analyses/{a2['analysis_id']}/zones?zone_type=new_flood").json()["features"]
        assert len(only_new) == len(by_type["new_flood"])
        ok(f"zone_type=new_flood returns just those {len(only_new)} polygons")

        cur.execute("SELECT baseline_method, permanent_water_area_km2, new_flood_area_km2, water_area_km2 "
                    "FROM flood_analysis WHERE analysis_id = %s", (a2["analysis_id"],))
        m, p, n, t = cur.fetchone()
        assert m == "jrc" and abs(float(p) + float(n) - float(t)) < 1e-5
        ok("independent check in PostgreSQL: baseline 'jrc', permanent + new = total (the schema constraint holds)")

        # ------------------------------------------------------------ 6
        print("\n--- 6. Reading analyses back ---")
        assert client.get(f"/api/analyses/{a1['analysis_id']}").json() == a1
        assert client.get(f"/api/analyses/{a2['analysis_id']}").json() == a2
        ok("GET /api/analyses/{id} returns exactly what the upload returned")
        ids = [a["analysis_id"] for a in client.get("/api/analyses").json()]
        assert ids == [a2["analysis_id"], a1["analysis_id"]]
        assert len(client.get(f"/api/analyses?event_id={event_id}").json()) == 2
        assert client.get("/api/analyses?event_id=999999").json() == []
        assert len(client.get("/api/analyses?limit=1").json()) == 1
        assert client.get("/api/analyses?limit=0").status_code == 422
        ok("list: newest first, event filter, paging; limit 0 is refused")
        for bad in ("0", "abc", "99999999999999999999"):
            assert client.get(f"/api/analyses/{bad}").status_code == 422
        assert client.get("/api/analyses/999999").status_code == 404
        ok("bad ids -> 422, unknown id -> 404")

        r = client.get(a1["mask_url"])
        assert r.status_code == 200 and r.headers["content-type"] == "image/tiff"
        mask_file = tmp / "downloaded.tif"
        mask_file.write_bytes(r.content)
        with rasterio.open(mask_file) as b:
            assert b.crs == crs and b.transform == transform and (b.height, b.width) == (H, W)
            assert int((b.read(1) == 1).sum()) == a1["water_pixels"]
        ok("mask download: same grid as the input, and its water pixels equal the stored count")

        # ------------------------------------------------------------ 7
        print("\n--- 7. Dashboard statistics ---")
        r = client.get("/api/stats/dashboard")
        assert r.status_code == 200, r.text
        d = r.json()
        total_water = scalar(cur, "SELECT sum(water_area_km2) FROM flood_analysis")
        assert d["analyses_completed"] == 2 and d["analyses_with_baseline"] == 1
        assert d["events"] == scalar(cur, "SELECT count(*) FROM disaster_events") == 1
        assert d["images"] == 2 and d["zone_polygons"] == scalar(cur, "SELECT count(*) FROM flood_zones")
        assert abs(d["total_water_area_km2"] - float(total_water)) < 1e-4
        assert abs(d["total_water_area_km2"] - 2 * 10.74337) < 0.001
        assert abs(d["total_new_flood_area_km2"] - 3.868805) < 0.0002
        assert abs(d["total_permanent_water_area_km2"] - 6.874565) < 0.0002
        assert d["latest_analysis_at"] and "counted twice" in d["note"]
        ok(f"events {d['events']}, analyses {d['analyses_completed']} ({d['analyses_with_baseline']} with baseline), "
           f"{d['zone_polygons']} polygons, water {d['total_water_area_km2']:.2f} km2, "
           f"new flood {d['total_new_flood_area_km2']:.2f} km2 (only the baseline analysis counts)")

        # ------------------------------------------------------------ 8
        print("\n--- 8. Bad requests are refused and leave nothing behind ---")
        shifted = write_tif(tmp / "shifted.tif", np.zeros((1, H, W)), crs, transform * Affine.translation(100, 0))
        cases = [
            ("unknown event", {**fields, "event_id": "999999"}, None, 404, "Event"),
            ("unknown source", {**fields, "source_id": "999999"}, None, 404, "source"),
            ("missing event_id", {"source_id": str(source_id)}, None, 422, None),
            ("baseline with 2 bands", fields, ("b.tif", write_tif(tmp / "b2.tif", np.zeros((2, H, W)), crs, transform)), 422, "band"),
            ("baseline of the wrong size", fields, ("b.tif", write_tif(tmp / "bs.tif", np.zeros((1, 100, 100)), crs, transform)), 422, "same size"),
            ("baseline in another coordinate system", fields, ("b.tif", write_tif(tmp / "bc.tif", np.zeros((1, H, W)), "EPSG:3857", transform)), 422, "coordinate system"),
            ("baseline covering a different area", fields, ("b.tif", shifted), 422, "same area"),
            ("baseline that is not an image", fields, ("b.tif", b"not an image"), 422, "could not be read"),
            ("baseline that is a .txt file", fields, ("b.txt", b"x"), 415, "GeoTIFF"),
        ]
        for label, case_fields, baseline, status, fragment in cases:
            counts, folders = db_counts(cur), snapshot(tmp)
            r = post(client, case_fields, baseline=baseline)
            assert r.status_code == status, f"{label}: expected {status}, got {r.status_code} {r.text}"
            if fragment:
                assert fragment in r.json()["detail"], f"{label}: {r.json()}"
            assert db_counts(cur) == counts, f"{label}: database rows were added"
            assert snapshot(tmp) == folders, f"{label}: files were left behind"
            ok(f"{label} -> {status}")
        three = write_tif(tmp / "three.tif", np.random.randn(3, 64, 64), "EPSG:4326",
                          Affine(0.0001, 0, 92.9, 0, -0.0001, 26.6), dtype="float32")
        counts = db_counts(cur)
        r = post(client, fields, image=("three.tif", three))
        assert r.status_code == 422 and "band" in r.json()["detail"] and db_counts(cur) == counts
        ok("a 3-band image -> 422, nothing stored")

        # ------------------------------------------------------------ 9
        print("\n--- 9. When the model is not available ---")
        real = app.state.model_service
        broken = ModelService(tmp / "missing.pth")
        broken.load()
        app.state.model_service = broken
        counts, folders = db_counts(cur), snapshot(tmp)
        r = post(client, fields)
        assert r.status_code == 503 and db_counts(cur) == counts and snapshot(tmp) == folders
        ok("POST /api/analyses -> 503; nothing stored")
        app.state.model_service = real
        r = post(client, fields)
        assert r.status_code == 201
        ok("with the real model back, analyses work again")

    app.dependency_overrides.clear()
    engine.dispose()
    rebuild(cur, BUILD_FILES[:3] + ("sample_data.sql",))
    conn.close()
    print("\n  Test database reset to the sample data.")
    print("\n" + SEP)
    print("  Analyses API tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
