"""
GeoFlood AI - Phase 17b test: the impact endpoints.

Sections 1-8 use the fabricated sample layout from database/sample_data.sql (answers known by hand,
the same ones database/test_impact.py checked). Section 9 runs a real analysis of India_591317 and
checks the API's counts against independent SQL. The reference features are fabricated demo
points, so section 9 tests consistency, not real flooding.

DESTRUCTIVE: rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m backend.test_impact_api
"""

import os
import tempfile
from pathlib import Path

import geopandas as gpd
import psycopg2
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from shapely.geometry import shape
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai.src import config
from backend.config import Settings, get_settings
from backend.database import get_db
from backend.main import app

DB_DIR = config.ROOT / "database"
SEP = "=" * 70
BUILD_FILES = ("reset.sql", "schema.sql", "impact_analysis.sql", "sample_data.sql")
CHIP = config.IMG_DIR / "India_591317_S1Hand.tif"
JRC = config.RAW_DIR / "JRCWaterHand" / "India_591317_JRCWaterHand.tif"
IMPACT_TABLES = ("affected_villages", "affected_roads", "agricultural_areas", "critical_infrastructure")
EXPECTED = {"villages": 2, "roads": 2, "farmland": 2, "infrastructure": 3}


def ok(message):
    print(f"  [OK] {message}")


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def rebuild(cur):
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())


def impact_rows(cur):
    return sum(scalar(cur, f"SELECT count(*) FROM {t}") for t in IMPACT_TABLES)


def get_json(client, url):
    r = client.get(url)
    assert r.status_code == 200, f"{url}: {r.status_code} {r.text}"
    return r.json()


def by_name(collection):
    return {f["properties"]["name"]: f for f in collection["features"]}


def utm_length_km(geometry):
    s = gpd.GeoSeries([geometry], crs="EPSG:4326")
    return float(s.to_crs(s.estimate_utm_crs()).length.iloc[0]) / 1000


def utm_area_km2(geometry):
    s = gpd.GeoSeries([geometry], crs="EPSG:4326")
    return float(s.to_crs(s.estimate_utm_crs()).area.iloc[0]) / 1e6


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 17b Impact API Test")
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

    # ---------------------------------------------------------------- 1
    print("\n--- 1. Build the test database (schema + functions + fabricated sample layout) ---")
    rebuild(cur)
    aid = scalar(cur, "SELECT analysis_id FROM flood_analysis ORDER BY analysis_id LIMIT 1")
    ok(f"sample analysis id = {aid} (baseline 'jrc', two new_flood zones, one permanent-water zone)")

    engine = create_engine(test_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False)

    def use_test_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = use_test_db
    with tempfile.TemporaryDirectory() as tmp_name, TestClient(app) as client:
        tmp = Path(tmp_name)
        settings = Settings(uploads_dir=tmp / "uploads", outputs_dir=tmp / "outputs")
        app.dependency_overrides[get_settings] = lambda: settings
        base = f"/api/analyses/{aid}"

        # ------------------------------------------------------------ 2
        print("\n--- 2. Before anything is computed ---")
        s = get_json(client, f"{base}/impact")
        assert s["zone_type"] == "new_flood" and s["baseline_method"] == "jrc"
        assert s["last_computed_at"] is None and "check last_computed_at" in s["note"]
        assert s["villages"] == {"count": 0, "inside": 0, "near": 0}
        assert s["roads"]["count"] == 0 and s["farmland"]["count"] == 0 and s["infrastructure"]["count"] == 0
        assert get_json(client, f"{base}/impact/villages")["features"] == []
        ok("summary is all zero with last_computed_at = null; the zone class defaults to new_flood "
           "because the analysis has a baseline")

        # ------------------------------------------------------------ 3
        print("\n--- 3. POST /impact (default: new_flood, 500 m) ---")
        r = client.post(f"{base}/impact")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["zone_type"] == "new_flood" and j["near_m"] == 500 and "not on the baseline" in j["compared_against"]
        assert {k: j[k] for k in EXPECTED} == EXPECTED, j
        ok(f"villages {j['villages']}, roads {j['roads']}, farmland {j['farmland']}, "
           f"infrastructure {j['infrastructure']} (the hand-checked layout)")
        total_rows = impact_rows(cur)
        assert total_rows == 9
        ok("9 rows stored in the four impact tables")

        # ------------------------------------------------------------ 4
        print("\n--- 4. Summary after computing ---")
        s = get_json(client, f"{base}/impact")
        assert s["last_computed_at"] is not None
        assert s["villages"] == {"count": 2, "inside": 2, "near": 0}
        assert s["roads"]["count"] == 2 and 1.545 <= s["roads"]["flooded_length_km"] <= 1.555
        assert s["farmland"]["count"] == 2 and 0.440 <= s["farmland"]["flooded_area_km2"] <= 0.443
        inf = s["infrastructure"]
        assert (inf["count"], inf["inside"], inf["near"]) == (3, 1, 2)
        assert inf["by_category"] == {"hospital": {"inside": 1, "near": 0},
                                      "school": {"inside": 0, "near": 1},
                                      "shelter": {"inside": 0, "near": 1}}, inf["by_category"]
        ok(f"villages 2 (2 inside); roads 2, {s['roads']['flooded_length_km']} km flooded; "
           f"farmland 2, {s['farmland']['flooded_area_km2']} km2 flooded")
        ok("infrastructure 3 = 1 inside + 2 near; by category: hospital inside, school and shelter near")

        # ------------------------------------------------------------ 5
        print("\n--- 5. The four GeoJSON layers ---")
        vill = get_json(client, f"{base}/impact/villages")
        assert vill["type"] == "FeatureCollection" and vill["zone_type"] == "new_flood"
        v = by_name(vill)
        assert set(v) == {"DEMO Village Alpha", "DEMO Village Beta"}
        for f in v.values():
            assert f["geometry"]["type"] == "Point"
            assert f["properties"]["relation"] == "inside" and f["properties"]["distance_m"] == 0
        ok("villages: Alpha and Beta, as Points, both 'inside'")

        roads = by_name(get_json(client, f"{base}/impact/roads"))
        assert set(roads) == {"DEMO Road R1", "DEMO Road R3"}
        for name, f in roads.items():
            g = shape(f["geometry"])
            assert f["geometry"]["type"] == "MultiLineString"
            independent, stored = utm_length_km(g), f["properties"]["flooded_length_km"]
            assert abs(independent - stored) / independent < 0.005, (name, independent, stored)
        assert 49.5 <= roads["DEMO Road R1"]["properties"]["flooded_pct"] <= 50.5
        assert 33.0 <= roads["DEMO Road R3"]["properties"]["flooded_pct"] <= 33.7
        ok("roads: R1 (50%) and R3 (33%); each geometry is the FLOODED PART, and its length measured "
           "independently (Shapely + UTM) matches the stored value")

        farm = by_name(get_json(client, f"{base}/impact/farmland"))
        assert set(farm) == {"DEMO Field F1", "DEMO Field F2"}
        for name, f in farm.items():
            g = shape(f["geometry"])
            assert f["geometry"]["type"] == "MultiPolygon"
            independent, stored = utm_area_km2(g), f["properties"]["flooded_area_km2"]
            assert abs(independent - stored) / independent < 0.005, (name, independent, stored)
        assert 49.8 <= farm["DEMO Field F1"]["properties"]["flooded_pct"] <= 50.2
        assert farm["DEMO Field F2"]["properties"]["flooded_pct"] >= 99.99
        ok("farmland: F1 (50%) and F2 (100%); flooded-part areas match an independent calculation")

        infra = by_name(get_json(client, f"{base}/impact/infrastructure"))
        assert set(infra) == {"DEMO Hospital H1", "DEMO School S1", "DEMO Shelter SH1"}
        assert {f["geometry"]["type"] for f in infra.values()} == {"Point"}
        h1, s1, sh1 = (infra[k]["properties"] for k in ("DEMO Hospital H1", "DEMO School S1", "DEMO Shelter SH1"))
        assert (h1["relation"], h1["distance_m"], h1["category"]) == ("inside", 0, "hospital")
        assert s1["relation"] == "near" and 240 <= s1["distance_m"] <= 258 and s1["category"] == "school"
        assert sh1["relation"] == "near" and 380 <= sh1["distance_m"] <= 396 and sh1["category"] == "shelter"
        ok(f"infrastructure: hospital inside; school near ({s1['distance_m']:.0f} m); "
           f"shelter near ({sh1['distance_m']:.0f} m)")

        # ------------------------------------------------------------ 6
        print("\n--- 6. Changing the 'near' distance, and re-running ---")
        j = client.post(f"{base}/impact?near_m=300").json()
        assert j["near_m"] == 300 and j["infrastructure"] == 2 and j["villages"] == 2
        assert set(by_name(get_json(client, f"{base}/impact/infrastructure"))) == {"DEMO Hospital H1", "DEMO School S1"}
        ok("near_m = 300: the shelter (about 388 m) drops out; the school (about 249 m) stays")
        j = client.post(f"{base}/impact?near_m=1000").json()
        assert j["villages"] == 3
        gamma = by_name(get_json(client, f"{base}/impact/villages"))["DEMO Village Gamma"]["properties"]
        assert gamma["relation"] == "near" and 735 <= gamma["distance_m"] <= 755
        ok(f"near_m = 1000: Village Gamma appears as 'near' at {gamma['distance_m']:.0f} m")
        assert get_json(client, f"{base}/impact")["villages"] == {"count": 3, "inside": 2, "near": 1}
        client.post(f"{base}/impact?near_m=500")
        client.post(f"{base}/impact?near_m=500")
        assert impact_rows(cur) == total_rows
        ok(f"back to 500 m, run twice: still exactly {total_rows} rows (no duplicates)")

        # ------------------------------------------------------------ 7
        print("\n--- 7. The zone class can be chosen, and classes stay apart ---")
        j = client.post(f"{base}/impact?zone_type=water").json()
        assert j["zone_type"] == "water" and {k: j[k] for k in EXPECTED} == {k: 0 for k in EXPECTED}
        assert impact_rows(cur) == total_rows
        s_water = get_json(client, f"{base}/impact?zone_type=water")
        assert s_water["villages"]["count"] == 0 and s_water["last_computed_at"] is None
        assert get_json(client, f"{base}/impact?zone_type=new_flood")["villages"]["count"] == 2
        assert get_json(client, f"{base}/impact")["zone_type"] == "new_flood"
        ok("zone_type=water finds nothing here (this analysis has no 'water' zones) and leaves the "
           "new_flood results untouched")

        # ------------------------------------------------------------ 8
        print("\n--- 8. Bad requests ---")
        for method, url in (("POST", "/api/analyses/999999/impact"), ("GET", "/api/analyses/999999/impact"),
                            ("GET", "/api/analyses/999999/impact/roads")):
            assert client.request(method, url).status_code == 404, url
        ok("an analysis that does not exist -> 404 on all three endpoints")
        assert client.get(f"{base}/impact/bogus").status_code == 422
        for bad in ("0", "abc", "99999999999999999999"):
            assert client.get(f"/api/analyses/{bad}/impact").status_code == 422
        for query in ("near_m=-1", "near_m=10001", "near_m=abc", "zone_type=bogus", "zone_type=permanent_water"):
            assert client.post(f"{base}/impact?{query}").status_code == 422, query
        assert impact_rows(cur) == total_rows
        ok("unknown layer, bad ids, negative or too large near_m, and a bad zone_type -> 422; nothing changed")

        # ------------------------------------------------------------ 9
        print("\n--- 9. A real analysis of India_591317, end to end (fabricated reference features) ---")
        event_id = scalar(cur, "SELECT event_id FROM disaster_events ORDER BY event_id LIMIT 1")
        sources = {x["name"]: x["source_id"] for x in client.get("/api/sources").json()}
        r = client.post("/api/analyses",
                        data={"event_id": str(event_id),
                              "source_id": str(sources["Sen1Floods11 hand-labeled chips"])},
                        files={"file": (CHIP.name, CHIP.read_bytes(), "image/tiff"),
                               "baseline_file": (JRC.name, JRC.read_bytes(), "image/tiff")})
        assert r.status_code == 201, r.text
        real_id = r.json()["analysis_id"]
        assert real_id != aid and r.json()["zone_count"] == 52
        j = client.post(f"/api/analyses/{real_id}/impact").json()
        counts = {k: j[k] for k in EXPECTED}

        cur.execute("""
            WITH u AS (SELECT ST_UnaryUnion(ST_Collect(geom)) AS g FROM flood_zones
                        WHERE analysis_id = %s AND zone_type = 'new_flood')
            SELECT
              (SELECT count(*) FROM reference_features f, u WHERE f.layer = 'village'
                  AND ST_DWithin(f.geom::geography, u.g::geography, 500)),
              (SELECT count(*) FROM reference_features f, u WHERE f.layer = 'road'
                  AND NOT ST_IsEmpty(ST_CollectionExtract(ST_Intersection(f.geom, u.g), 2))),
              (SELECT count(*) FROM reference_features f, u WHERE f.layer = 'farmland'
                  AND NOT ST_IsEmpty(ST_CollectionExtract(ST_Intersection(ST_MakeValid(f.geom), u.g), 3))),
              (SELECT count(*) FROM reference_features f, u WHERE f.layer = 'infrastructure'
                  AND ST_DWithin(f.geom::geography, u.g::geography, 500))""", (real_id,))
        independent = dict(zip(EXPECTED, cur.fetchone()))
        assert counts == independent, f"API {counts} vs independent SQL {independent}"
        ok(f"the API's counts {counts} equal an independent SQL query on the real polygons")
        for layer, n in counts.items():
            assert len(get_json(client, f"/api/analyses/{real_id}/impact/{layer}")["features"]) == n
        ok("each GeoJSON layer has exactly as many features as the count says")
        s = get_json(client, f"/api/analyses/{real_id}/impact")
        assert s["villages"]["count"] == counts["villages"] and s["roads"]["count"] == counts["roads"]
        assert get_json(client, f"{base}/impact")["villages"]["count"] == 2
        ok("the summary agrees; the other analysis's results were not touched")
        print("       NOTE: the reference features are fabricated demo points, so these counts say")
        print("       nothing about real flooding. Real villages and roads arrive in Phase 21.")

    app.dependency_overrides.clear()
    engine.dispose()
    rebuild(cur)
    cur.execute("SELECT * FROM compute_impact(%s)", (aid,))
    conn.close()
    print("\n  Test database reset to the sample layout, with impact computed for the sample analysis.")
    print("\n" + SEP)
    print("  Impact API tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
