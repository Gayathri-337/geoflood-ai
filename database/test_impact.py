"""
GeoFlood AI - Phase 14b test: helper functions, compute_impact() and spatial_queries.sql.

DESTRUCTIVE like test_schema.py: it rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m database.test_impact
"""

import os
import subprocess

import geopandas as gpd
import psycopg2
from dotenv import load_dotenv
from pyproj import Geod
from shapely import wkb

from ai.src import config
from gis.area_calculator import geographic_cell_area_km2, polygon_area_km2

DB_DIR = config.ROOT / "database"
SEP = "=" * 70
BUILD_FILES = ("reset.sql", "schema.sql", "impact_analysis.sql", "sample_data.sql")
IMPACT_TABLES = ("affected_villages", "affected_roads", "agricultural_areas", "critical_infrastructure")
RAISE_EXCEPTION = "P0001"


def rows(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def scalar(cur, sql, params=None):
    return rows(cur, sql, params)[0][0]


def ok(message):
    print(f"  [OK] {message}")


def rebuild(cur):
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())


def impact(cur, aid, zone=None, near=500):
    return dict(rows(cur, "SELECT layer_name, features_affected FROM compute_impact(%s, %s, %s)",
                     (aid, zone, near)))


def named(cur, table, aid, columns, zone="new_flood"):
    """{feature name: (column values as floats or text)} for one impact table."""
    cols = ", ".join(f"t.{c}" for c in columns)
    data = rows(cur, f"SELECT f.name, {cols} FROM {table} t "
                     "JOIN reference_features f ON f.feature_id = t.feature_id "
                     "WHERE t.analysis_id = %s AND t.zone_type = %s ORDER BY f.name", (aid, zone))
    return {r[0]: tuple(v if isinstance(v, str) or v is None else float(v) for v in r[1:]) for r in data}


def impact_row_counts(cur):
    return tuple(scalar(cur, f"SELECT count(*) FROM {t}") for t in IMPACT_TABLES)


def expect_error(cur, label, sql, params, fragment):
    try:
        cur.execute(sql, params)
    except psycopg2.Error as err:
        assert err.pgcode == RAISE_EXCEPTION and fragment in str(err), f"{label}: unexpected error {err}"
        ok(f"rejected: {label}")
        return
    raise AssertionError(f"{label}: the function ACCEPTED bad input!")


def fetch_geom(cur, sql, params=None):
    cur.execute(sql, params)
    return wkb.loads(bytes(cur.fetchone()[0]))


def length_km(geom):
    series = gpd.GeoSeries([geom], crs="EPSG:4326")
    return float(series.to_crs(series.estimate_utm_crs()).length.iloc[0]) / 1000


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 14b Impact Analysis Test")
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
    db = scalar(cur, "SELECT current_database()")
    if "test" not in db:
        raise SystemExit(f"Refusing to run: database '{db}' does not look like a test database.")
    print(f"\nTest database: {db}")

    # ---------------------------------------------------------------- 1
    print("\n--- 1. Build: reset + schema + impact_analysis + sample data ---")
    rebuild(cur)
    funcs = {r[0] for r in rows(cur, "SELECT proname FROM pg_proc WHERE proname IN "
                                     "('compute_impact', 'geo_area_km2', 'geo_length_km')")}
    assert funcs == {"compute_impact", "geo_area_km2", "geo_length_km"}, funcs
    aid = scalar(cur, "SELECT analysis_id FROM flood_analysis ORDER BY analysis_id LIMIT 1")
    ok(f"3 functions created; sample analysis id = {aid}")

    # ---------------------------------------------------------------- 2
    print("\n--- 2. Helper functions against independent references ---")
    mine = float(scalar(cur, "SELECT geo_area_km2(ST_MakeEnvelope(78.0, 17.38, 78.01, 17.39, 4326))"))
    ref = float(geographic_cell_area_km2(17.38, 17.39, 0.01))     # exact formula from Phase 12
    assert abs(mine - ref) / ref < 1e-4, (mine, ref)
    ok(f"geo_area_km2: {mine:.4f} km2 in SQL vs {ref:.4f} km2 from the Phase 12 formula")
    sql_len = float(scalar(cur, "SELECT geo_length_km(ST_GeomFromText('LINESTRING(92 26, 92 26.1)', 4326))"))
    py_len = Geod(ellps="WGS84").inv(92, 26, 92, 26.1)[2] / 1000
    assert abs(sql_len - py_len) / py_len < 1e-4, (sql_len, py_len)
    ok(f"geo_length_km: {sql_len:.4f} km in SQL vs {py_len:.4f} km from pyproj")
    zeros = rows(cur, "SELECT geo_area_km2(ST_GeomFromText('POLYGON EMPTY', 4326)), "
                      "geo_area_km2(NULL::geometry), geo_length_km(NULL::geometry)")[0]
    assert all(float(v) == 0 for v in zeros)
    ok("empty and NULL geometries give 0 (no crash)")

    # ---------------------------------------------------------------- 3
    print("\n--- 3. compute_impact(), automatic zone class, 500 m ---")
    result = impact(cur, aid)
    for layer, count in result.items():
        print(f"       {layer:<15}{count}")
    assert result == {"village": 2, "road": 2, "farmland": 2, "infrastructure": 3}, result
    ok("counts match the hand-checked layout (the zone class was 'new_flood', chosen from the JRC baseline)")

    vill = named(cur, "affected_villages", aid, ["relation", "distance_m"])
    assert set(vill) == {"DEMO Village Alpha", "DEMO Village Beta"}
    assert all(v == ("inside", 0.0) for v in vill.values())
    ok("villages: Alpha and Beta inside; Gamma (about 745 m away) and Delta (river only) not included")

    roads = named(cur, "affected_roads", aid, ["flooded_length_km", "flooded_pct"])
    assert set(roads) == {"DEMO Road R1", "DEMO Road R3"}, roads
    r1, r3 = roads["DEMO Road R1"], roads["DEMO Road R3"]
    assert 0.990 <= r1[0] <= 1.002 and 49.5 <= r1[1] <= 50.5, r1
    assert 0.550 <= r3[0] <= 0.558 and 33.0 <= r3[1] <= 33.7, r3
    ok(f"roads: R1 {r1[0]:.3f} km flooded ({r1[1]:.1f}%), R3 {r3[0]:.3f} km ({r3[1]:.1f}%); R2 not included")

    farm = named(cur, "agricultural_areas", aid, ["flooded_area_km2", "flooded_pct"])
    assert set(farm) == {"DEMO Field F1", "DEMO Field F2"}, farm
    f1, f2 = farm["DEMO Field F1"], farm["DEMO Field F2"]
    assert 0.262 <= f1[0] <= 0.268 and 49.8 <= f1[1] <= 50.2, f1
    assert 0.174 <= f2[0] <= 0.179 and f2[1] >= 99.99, f2
    ok(f"farmland: F1 {f1[0]:.4f} km2 ({f1[1]:.1f}%), F2 {f2[0]:.4f} km2 ({f2[1]:.1f}%); F3 not included")

    infra = named(cur, "critical_infrastructure", aid, ["relation", "distance_m"])
    assert set(infra) == {"DEMO Hospital H1", "DEMO School S1", "DEMO Shelter SH1"}, infra
    assert infra["DEMO Hospital H1"] == ("inside", 0.0)
    s1, sh1 = infra["DEMO School S1"], infra["DEMO Shelter SH1"]
    assert s1[0] == "near" and 240 <= s1[1] <= 258, s1
    assert sh1[0] == "near" and 380 <= sh1[1] <= 396, sh1
    ok(f"infrastructure: H1 inside, S1 near ({s1[1]:.0f} m), SH1 near ({sh1[1]:.0f} m); Bridge BR1 not included")

    # ---------------------------------------------------------------- 4
    print("\n--- 4. Independent cross-check: Shapely + UTM 46N instead of PostGIS ---")
    flood = fetch_geom(cur, "SELECT ST_AsBinary(ST_UnaryUnion(ST_Collect(geom))) FROM flood_zones "
                            "WHERE analysis_id = %s AND zone_type = 'new_flood'", (aid,))
    for name, stored in farm.items():
        geom = fetch_geom(cur, "SELECT ST_AsBinary(geom) FROM reference_features WHERE name = %s", (name,))
        python_km2 = polygon_area_km2(gpd.GeoDataFrame(geometry=[geom.intersection(flood)], crs="EPSG:4326"))
        assert abs(python_km2 - stored[0]) / python_km2 < 0.005, (name, python_km2, stored[0])
        ok(f"{name}: flooded area {stored[0]:.4f} km2 in PostGIS vs {python_km2:.4f} km2 by Shapely/UTM")
    for name, stored in roads.items():
        geom = fetch_geom(cur, "SELECT ST_AsBinary(geom) FROM reference_features WHERE name = %s", (name,))
        python_km = length_km(geom.intersection(flood))
        assert abs(python_km - stored[0]) / python_km < 0.005, (name, python_km, stored[0])
        ok(f"{name}: flooded length {stored[0]:.4f} km in PostGIS vs {python_km:.4f} km by Shapely/UTM")

    # ---------------------------------------------------------------- 5
    print("\n--- 5. Re-running and changing the 'near' distance ---")
    before = impact_row_counts(cur)
    assert impact(cur, aid) == result and impact_row_counts(cur) == before
    ok(f"second run gives the same result and the same {sum(before)} rows (no duplicates)")

    r300 = impact(cur, aid, near=300)
    assert r300["infrastructure"] == 2 and r300["village"] == 2, r300
    ok("near = 300 m: S1 (about 249 m) stays, SH1 (about 388 m) drops out -> 2 infrastructure features")
    r200 = impact(cur, aid, near=200)
    assert r200["infrastructure"] == 1, r200
    ok("near = 200 m: only the hospital inside the flood remains -> 1 infrastructure feature")
    r1000 = impact(cur, aid, near=1000)
    assert r1000["village"] == 3 and r1000["infrastructure"] == 3, r1000
    gamma = named(cur, "affected_villages", aid, ["relation", "distance_m"])["DEMO Village Gamma"]
    assert gamma[0] == "near" and 735 <= gamma[1] <= 755, gamma
    ok(f"near = 1000 m: Village Gamma appears as 'near' at {gamma[1]:.0f} m -> 3 villages")
    assert impact(cur, aid, near=500) == result
    ok("back to 500 m: original result restored")

    # ---------------------------------------------------------------- 6
    print("\n--- 6. Zone classes are kept apart ---")
    counts = impact_row_counts(cur)
    assert impact(cur, aid, "water") == {"village": 0, "road": 0, "farmland": 0, "infrastructure": 0}
    assert impact_row_counts(cur) == counts
    ok("zone class 'water' has no zones in this analysis -> zero results, and the new_flood rows are untouched")

    # ---------------------------------------------------------------- 7
    print("\n--- 7. Bad input is rejected ---")
    expect_error(cur, "an analysis that does not exist",
                 "SELECT * FROM compute_impact(%s, NULL, 500)", (999999,), "does not exist")
    expect_error(cur, "zone class 'permanent_water'",
                 "SELECT * FROM compute_impact(%s, 'permanent_water', 500)", (aid,), "water or new_flood")
    expect_error(cur, "a negative near distance",
                 "SELECT * FROM compute_impact(%s, NULL, -5)", (aid,), "near distance")

    # ---------------------------------------------------------------- 8
    print("\n--- 8. database/spatial_queries.sql runs and gives the right names ---")
    proc = subprocess.run(
        ["psql", test_url, "-v", "ON_ERROR_STOP=1", "-v", f"aid={aid}", "-v", "zone=new_flood",
         "-v", "near=500", "-f", str(DB_DIR / "spatial_queries.sql")],
        capture_output=True, text=True)
    assert proc.returncode == 0 and "ERROR" not in proc.stderr, proc.stderr
    for expected in ("DEMO Village Alpha", "DEMO Village Beta", "DEMO Road R1", "DEMO Road R3",
                     "DEMO Field F1", "DEMO Field F2", "DEMO Hospital H1"):
        assert expected in proc.stdout, f"{expected} missing from the query output"
    for unexpected in ("DEMO Village Gamma", "DEMO Road R2", "DEMO Field F3", "DEMO Bridge BR1"):
        assert unexpected not in proc.stdout, f"{unexpected} should not be in the output"
    ok("all 8 queries ran without errors; affected features listed, unaffected ones absent")
    print("\n" + proc.stdout.rstrip())

    # ---------------------------------------------------------------- 9
    print("\n--- 9. Deleting an analysis removes its impact rows ---")
    cur.execute("DELETE FROM flood_analysis")
    assert impact_row_counts(cur) == (0, 0, 0, 0)
    assert scalar(cur, "SELECT count(*) FROM reference_features") == 14
    ok("impact tables are empty; reference features untouched")

    rebuild(cur)
    aid = scalar(cur, "SELECT analysis_id FROM flood_analysis ORDER BY analysis_id LIMIT 1")
    impact(cur, aid)
    conn.close()
    print(f"\n  The test database now holds the sample data plus its impact results (analysis {aid}),")
    print("  so you can browse it in pgAdmin or run spatial_queries.sql yourself.")
    print("\n" + SEP)
    print("  Impact analysis tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
