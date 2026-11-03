"""
GeoFlood AI - Phase 21b test: OpenStreetMap features -> reference_features.

Part 1 (offline) converts a hand-made Overpass-style answer (fabricated elements that exercise every
rule) and checks the result. Part 2 loads the same elements into the TEST database next to the sample
analysis and checks that compute_impact() finds exactly the features expected by hand.

DESTRUCTIVE (part 2): rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m gis.test_osm_features
"""

import json
import os
import tempfile
import urllib.parse
from collections import Counter
from pathlib import Path

import geopandas as gpd
import psycopg2
from dotenv import load_dotenv
from shapely import wkb
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai.src import config
from gis import osm_features as of

DB_DIR = config.ROOT / "database"
SEP = "=" * 70
BUILD_FILES = ("reset.sql", "schema.sql", "impact_analysis.sql", "sample_data.sql")
W, S = 92.915, 26.585          # south-west corner of the fixture, next to the sample flood zones
STAMP = "2026-11-02T10:00:00Z"


def ok(message):
    print(f"  [OK] {message}")


def make_payload(village_name="Alpha"):
    """Fabricated Overpass answer. Offsets are in degrees from (W, S); zone A of the sample analysis
    is offsets 0.005-0.015 east / 0.005-0.015 north, zone B is 0.025-0.030 / 0.025-0.030."""
    def pt(dx, dy):
        return (round(W + dx, 6), round(S + dy, 6))

    def node(i, dx, dy, **tags):
        lon, lat = pt(dx, dy)
        return {"type": "node", "id": i, "lat": lat, "lon": lon, "tags": tags}

    def way(i, offsets, **tags):
        coords = [pt(dx, dy) for dx, dy in offsets]
        return {"type": "way", "id": i, "nodes": list(range(len(coords))),
                "geometry": [{"lat": lat, "lon": lon} for lon, lat in coords], "tags": tags}

    def rect(x0, y0, x1, y1):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]

    elements = [
        node(1, 0.010, 0.010, place="village", name=village_name),              # inside zone A
        node(2, 0.0275, 0.0275, place="hamlet"),                                # inside zone B, no name
        node(3, 0.080, 0.080, place="town", name="Big Town"),                   # not one of our layers
        node(60, 0.050, 0.050, place="village", amenity="school", name="Both"), # village wins over school
        way(40, rect(0.060, 0.060, 0.062, 0.062), place="village", name="Polygon Village"),
        way(10, [(0.000, 0.010), (0.040, 0.010)], highway="primary", ref="NH-TEST", name="Test Highway",
            note="not kept", source="survey"),                                  # crosses zone A
        way(11, [(0.0275, 0.020), (0.0275, 0.035)], highway="track"),           # crosses zone B
        way(12, [(0.050, 0.050)], highway="path"),                              # one point only
        way(13, [(0.000, 0.020), (0.010, 0.020)], highway="residential", name="x" * 300),  # long name
        way(20, rect(0.012, 0.008, 0.020, 0.012), landuse="farmland", name="Field F"),     # half in zone A
        way(21, [(0.070, 0.010), (0.075, 0.010), (0.075, 0.015)], landuse="farmland"),     # not closed
        way(22, [(0.070, 0.030), (0.075, 0.035), (0.075, 0.030), (0.070, 0.035), (0.070, 0.030)],
            landuse="meadow"),                                                  # bow-tie: self-intersecting
        node(31, 0.012, 0.012, amenity="hospital", name="Hospital H"),         # inside zone A
        way(30, rect(0.0170, 0.0090, 0.0172, 0.0092), amenity="school", name="School S"),  # about 199 m from A
        node(32, 0.090, 0.090, amenity="parking"),                              # not one of our layers
        {"type": "relation", "id": 50, "members": [], "tags": {"landuse": "farmland", "type": "multipolygon"}},
        node(1, 0.010, 0.010, place="village", name=village_name),              # the same node twice
    ]
    return {"version": 0.6, "osm3s": {"timestamp_osm_base": STAMP}, "elements": elements}


# ------------------------------------------------------------------ part 1
def part1(payload):
    features, skipped = of.parse_elements(payload)
    ref = {f["source_ref"]: f for f in features}

    assert Counter(f["layer"] for f in features) == {"village": 4, "road": 3, "farmland": 2, "infrastructure": 2}
    assert dict(skipped) == {"duplicate": 1, "unclassified": 2, "too_few_points": 1,
                             "not_a_closed_area": 1, "relations": 1}, dict(skipped)
    ok("11 features in the right layers: village 4, road 3, farmland 2, infrastructure 2")
    ok(f"skipped and counted: {dict(skipped)}")

    assert ref["node/1"]["geom"].geom_type == "Point" and ref["node/1"]["name"] == "Alpha"
    assert ref["node/2"]["name"] is None and ref["node/2"]["category"] == "hamlet"
    assert ref["way/40"]["geom"].geom_type == "Polygon" and ref["way/40"]["layer"] == "village"
    assert ref["node/60"]["layer"] == "village" and ref["node/60"]["category"] == "village"
    assert ref["way/10"]["geom"].geom_type == "LineString" and ref["way/10"]["category"] == "primary"
    assert ref["way/20"]["geom"].geom_type == "Polygon"
    assert ref["way/30"]["geom"].geom_type == "Polygon" and ref["way/30"]["category"] == "school"
    assert ref["node/31"]["geom"].geom_type == "Point" and ref["node/31"]["category"] == "hospital"
    ok("shapes and categories: points, lines and polygons as expected; an unnamed hamlet has name None; "
       "a node tagged both village and school becomes a village")

    road = ref["way/10"]
    assert road["name"] == "Test Highway" and set(road["properties"]["tags"]) == {"name", "ref", "highway"}
    assert road["properties"]["tags"]["ref"] == "NH-TEST"
    assert len(ref["way/13"]["name"]) == 200
    ok("only the whitelisted tags are kept (the 'note' and 'source' tags are dropped); a 300-character name is cut to 200")

    bow = ref["way/22"]["geom"]
    assert bow.is_valid and bow.geom_type in ("Polygon", "MultiPolygon") and bow.area > 0
    assert all(f["geom"].is_valid and not f["geom"].is_empty for f in features)
    assert all(f["properties"]["osm_data_timestamp"] == STAMP and f["properties"]["osm_id"] == f["source_ref"]
               for f in features)
    ok(f"the self-intersecting polygon was repaired ({bow.geom_type}); every geometry is valid; "
       "each feature carries its OSM id and the data timestamp")

    fc = of.to_geojson(features)
    again = json.loads(json.dumps(fc))
    first = next(f for f in again["features"] if f["properties"]["source_ref"] == "node/1")
    assert len(again["features"]) == 11 and first["geometry"]["coordinates"] == [92.925, 26.595]
    ok("GeoJSON export has 11 features; coordinates are [longitude, latitude]")

    assert of.parse_elements({"elements": []}) == ([], Counter())
    f2, s2 = of.parse_elements({"elements": [{"type": "way", "tags": {"highway": "x"}}, {"type": "bogus", "id": 1},
                                             {"type": "way", "id": 5, "tags": {"highway": "x"},
                                              "geometry": [{"lat": 1}, {"lon": 2}]}]})
    assert f2 == [] and s2["unreadable_element"] == 3
    ok("empty answers are fine; elements with missing ids or broken geometry are counted as unreadable, not fatal")

    box = (26.58438, 92.90736, 26.63038, 92.95335)
    big = of.expand_bbox(box, 600)
    assert big[0] < box[0] and big[1] < box[1] and big[2] > box[2] and big[3] > box[3]
    assert abs((box[0] - big[0]) - 0.00539) < 2e-5 and abs((box[1] - big[1]) - 0.00603) < 3e-5
    query = of.build_query(big)
    assert f"[bbox:{big[0]:.5f},{big[1]:.5f},{big[2]:.5f},{big[3]:.5f}]" in query and query.rstrip().endswith("out geom;")
    for value in sorted(of.PLACES | of.AMENITIES | of.LANDUSES) + ['way["highway"]']:
        assert value in query, value
    ok("a 600 m margin adds about 0.0054 degrees of latitude and 0.0060 of longitude; the query contains the box and "
       "every tag value")

    for bad, label in (({"remark": "runtime error: Query timed out", "elements": []}, "a timeout remark"),
                       ({"version": 0.6}, "no elements list")):
        try:
            of.check_response(bad)
        except ValueError:
            continue
        raise AssertionError(f"{label} should have been rejected")
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "chip.json"
        cache.write_text(json.dumps(payload))
        reloaded, skipped2 = of.parse_elements(json.loads(cache.read_text()))
        assert len(reloaded) == 11 and dict(skipped2) == dict(skipped)
    ok("unusable answers are rejected; a saved download gives the same result when read back")


# ------------------------------------------------------------------ part 2
def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def rows(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def rebuild(cur):
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())


def utm_length_km(geometry):
    s = gpd.GeoSeries([geometry], crs="EPSG:4326")
    return float(s.to_crs(s.estimate_utm_crs()).length.iloc[0]) / 1000


def utm_area_km2(geometry):
    s = gpd.GeoSeries([geometry], crs="EPSG:4326")
    return float(s.to_crs(s.estimate_utm_crs()).area.iloc[0]) / 1e6


def part2(payload):
    load_dotenv(config.ROOT / ".env")
    test_url, main_url = os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL")
    if not test_url:
        raise SystemExit("TEST_DATABASE_URL is missing from .env.")
    if test_url == main_url:
        raise SystemExit("TEST_DATABASE_URL must differ from DATABASE_URL: this test DROPS all tables.")
    conn = psycopg2.connect(test_url, connect_timeout=5)
    conn.autocommit = True
    cur = conn.cursor()
    db_name = scalar(cur, "SELECT current_database()")
    if "test" not in db_name:
        raise SystemExit(f"Refusing to run: database '{db_name}' does not look like a test database.")
    print(f"\nTest database: {db_name}")
    rebuild(cur)
    cur.execute("DELETE FROM reference_features")           # remove the DEMO features of the sample data
    aid = scalar(cur, "SELECT analysis_id FROM flood_analysis ORDER BY analysis_id LIMIT 1")

    engine = create_engine(test_url, pool_pre_ping=True)
    session = Session(engine)
    features, _ = of.parse_elements(payload)
    assert of.load_features(session, features) == 11
    session.commit()

    print("\n--- 2a. What was stored ---")
    assert dict(rows(cur, "SELECT layer, count(*) FROM reference_features GROUP BY layer")) == \
        {"village": 4, "road": 3, "farmland": 2, "infrastructure": 2}
    assert scalar(cur, "SELECT count(DISTINCT source) FROM reference_features") == 1
    assert scalar(cur, "SELECT bool_and(ST_IsValid(geom) AND source = 'openstreetmap' AND ST_SRID(geom) = 4326) "
                       "FROM reference_features")
    types = {}
    for layer, gtype in rows(cur, "SELECT layer, GeometryType(geom) FROM reference_features"):
        types.setdefault(layer, set()).add(gtype)
    assert types["road"] == {"LINESTRING"} and types["village"] == {"POINT", "POLYGON"}
    assert types["farmland"] <= {"POLYGON", "MULTIPOLYGON"} and types["infrastructure"] == {"POINT", "POLYGON"}
    ok("11 rows in the four layers; all geometries valid, SRID 4326, source 'openstreetmap'; "
       "the table's geometry-type rules accepted every one")
    osm_id, ref_tag, note_tag, stamp, name, category = rows(
        cur, "SELECT properties->>'osm_id', properties->'tags'->>'ref', properties->'tags'->>'note', "
             "properties->>'osm_data_timestamp', name, category FROM reference_features WHERE source_ref = 'way/10'")[0]
    assert (osm_id, ref_tag, note_tag, stamp, name, category) == ("way/10", "NH-TEST", None, STAMP, "Test Highway", "primary")
    ok("the JSON properties hold the OSM id, the kept tags and the data timestamp (the dropped tag is absent)")

    print("\n--- 2b. Loading again updates instead of duplicating ---")
    before = scalar(cur, "SELECT loaded_at FROM reference_features WHERE source_ref = 'node/1'")
    renamed, _ = of.parse_elements(make_payload(village_name="Alpha Renamed"))
    of.load_features(session, renamed)
    session.commit()
    assert scalar(cur, "SELECT count(*) FROM reference_features") == 11
    assert scalar(cur, "SELECT name FROM reference_features WHERE source_ref = 'node/1'") == "Alpha Renamed"
    assert scalar(cur, "SELECT loaded_at FROM reference_features WHERE source_ref = 'node/1'") > before
    of.load_features(session, features)
    session.commit()
    assert scalar(cur, "SELECT name FROM reference_features WHERE source_ref = 'node/1'") == "Alpha"
    assert scalar(cur, "SELECT count(*) FROM reference_features") == 11
    ok("a second load keeps exactly 11 rows, updates the changed name and the load time")

    print("\n--- 2c. The impact function on OpenStreetMap-format features ---")
    result = dict(rows(cur, "SELECT layer_name, features_affected FROM compute_impact(%s, NULL, 500)", (aid,)))
    assert result == {"village": 2, "road": 2, "farmland": 1, "infrastructure": 2}, result
    ok(f"compute_impact finds {result}")

    def refs(table):
        return {r[0]: r[1:] for r in rows(cur, f"SELECT f.source_ref, t.* FROM {table} t "
                                               "JOIN reference_features f ON f.feature_id = t.feature_id "
                                               "WHERE t.analysis_id = %s", (aid,))}
    cur.execute("SELECT f.source_ref FROM affected_villages t JOIN reference_features f USING (feature_id) "
                "WHERE t.analysis_id = %s", (aid,))
    assert {r[0] for r in cur.fetchall()} == {"node/1", "node/2"}
    ok("villages: the two nodes inside the flood zones; the far village node and the village polygon are not included")

    cur.execute("SELECT f.source_ref, t.flooded_length_km, t.flooded_pct, ST_AsBinary(t.flooded_geom) "
                "FROM affected_roads t JOIN reference_features f USING (feature_id) WHERE t.analysis_id = %s", (aid,))
    roads = {r[0]: r[1:] for r in cur.fetchall()}
    assert set(roads) == {"way/10", "way/11"}, set(roads)
    (len10, pct10, geom10), (len11, pct11, geom11) = roads["way/10"], roads["way/11"]
    assert 0.990 <= float(len10) <= 1.002 and 24.5 <= float(pct10) <= 25.5, (len10, pct10)
    assert 0.548 <= float(len11) <= 0.560 and 33.0 <= float(pct11) <= 33.7, (len11, pct11)
    for stored, geom in ((len10, geom10), (len11, geom11)):
        independent = utm_length_km(wkb.loads(bytes(geom)))
        assert abs(independent - float(stored)) / independent < 0.005
    ok(f"roads: way/10 {float(len10):.3f} km flooded ({float(pct10):.1f}% of the road), way/11 {float(len11):.3f} km "
       f"({float(pct11):.1f}%); lengths agree with an independent Shapely/UTM calculation")

    cur.execute("SELECT f.source_ref, t.flooded_area_km2, t.flooded_pct, ST_AsBinary(t.flooded_geom) "
                "FROM agricultural_areas t JOIN reference_features f USING (feature_id) WHERE t.analysis_id = %s", (aid,))
    farm = cur.fetchall()
    assert [r[0] for r in farm] == ["way/20"]
    _, area, pct, geom = farm[0]
    assert 0.130 <= float(area) <= 0.135 and 37.0 <= float(pct) <= 38.0, (area, pct)
    assert abs(utm_area_km2(wkb.loads(bytes(geom))) - float(area)) / float(area) < 0.005
    ok(f"farmland: field way/20 is {float(pct):.1f}% flooded ({float(area):.4f} km2); the repaired bow-tie field is far away and not included")

    cur.execute("SELECT f.source_ref, t.relation, t.distance_m FROM critical_infrastructure t "
                "JOIN reference_features f USING (feature_id) WHERE t.analysis_id = %s", (aid,))
    infra = {r[0]: r[1:] for r in cur.fetchall()}
    assert set(infra) == {"node/31", "way/30"}, infra
    assert infra["node/31"][0] == "inside" and float(infra["node/31"][1]) == 0
    assert infra["way/30"][0] == "near" and 195 <= float(infra["way/30"][1]) <= 204, infra["way/30"]
    ok(f"infrastructure: the hospital node is inside; the school polygon is near ({float(infra['way/30'][1]):.0f} m)")

    session.close()
    engine.dispose()
    rebuild(cur)
    conn.close()
    print("\n  Test database reset to the sample data.")


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 21b OSM Features Test")
    print(SEP)
    payload = make_payload()
    print("\n--- Part 1: conversion (offline, fabricated Overpass answer) ---")
    part1(payload)
    print("\n--- Part 2: loading into PostGIS and the impact function ---")
    part2(payload)
    print("\n" + SEP)
    print("  OSM features tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
