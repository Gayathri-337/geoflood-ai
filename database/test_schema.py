"""
GeoFlood AI - Phase 14a test: schema, sample data, constraints and relationships.

DESTRUCTIVE: it drops and rebuilds every GeoFlood table in the database named by
TEST_DATABASE_URL (never DATABASE_URL).

Usage (project root):  python -m database.test_schema
"""

import os

import psycopg2
from dotenv import load_dotenv

from ai.src import config

DB_DIR = config.ROOT / "database"
SEP = "=" * 70

TABLES = {"users", "satellite_sources", "disaster_events", "satellite_images", "flood_analysis",
          "flood_zones", "reference_features", "affected_villages", "affected_roads",
          "agricultural_areas", "critical_infrastructure", "flood_reports", "emergency_actions"}

GEOMETRY_COLUMNS = {
    ("disaster_events", "area_of_interest", "POLYGON"),
    ("satellite_images", "footprint", "POLYGON"),
    ("flood_zones", "geom", "MULTIPOLYGON"),
    ("reference_features", "geom", "GEOMETRY"),
    ("affected_roads", "flooded_geom", "MULTILINESTRING"),
    ("agricultural_areas", "flooded_geom", "MULTIPOLYGON"),
    ("emergency_actions", "location", "POINT"),
}

EXPECTED_ROWS = {
    "users": 2, "satellite_sources": 2, "disaster_events": 1, "satellite_images": 1,
    "flood_analysis": 1, "flood_zones": 3, "reference_features": 14, "flood_reports": 1,
    "emergency_actions": 2, "affected_villages": 0, "affected_roads": 0,
    "agricultural_areas": 0, "critical_infrastructure": 0,
}

CHECK_VIOLATION, UNIQUE_VIOLATION, FK_VIOLATION = "23514", "23505", "23503"


def rows(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def scalar(cur, sql, params=None):
    return rows(cur, sql, params)[0][0]


def rebuild(cur):
    for name in ("reset.sql", "schema.sql", "sample_data.sql"):
        cur.execute((DB_DIR / name).read_text())


def expect_fail(cur, label, sql, params=None, code=None, constraint=None):
    """The database must refuse this statement."""
    try:
        cur.execute(sql, params)
    except psycopg2.Error as err:
        if code and err.pgcode != code:
            raise AssertionError(f"{label}: expected SQLSTATE {code}, got {err.pgcode}\n{err.pgerror}")
        if constraint and err.diag.constraint_name != constraint:
            raise AssertionError(f"{label}: expected constraint {constraint}, "
                                 f"got {err.diag.constraint_name}")
        first = (err.pgerror or str(err)).strip().splitlines()[0]
        print(f"  [OK] rejected: {label}\n         {first}")
        return
    raise AssertionError(f"{label}: the database ACCEPTED bad data!")


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 14a Schema Test")
    print(SEP)

    load_dotenv(config.ROOT / ".env")
    test_url, main_url = os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL")
    if not test_url:
        raise SystemExit("TEST_DATABASE_URL is missing from .env (Step 14.1).")
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

    # ------------------------------------------------------------ 1
    print("\n--- 1. Build: reset.sql + schema.sql + sample_data.sql ---")
    rebuild(cur)
    found = {r[0] for r in rows(cur, "SELECT table_name FROM information_schema.tables "
                                     "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")}
    found.discard("spatial_ref_sys")          # PostGIS's own table
    assert found == TABLES, f"tables differ. Missing: {TABLES - found}  Extra: {found - TABLES}"
    print(f"  [OK] all {len(TABLES)} tables exist")

    # ------------------------------------------------------------ 2
    print("\n--- 2. Sample data: row counts ---")
    for table, expected in EXPECTED_ROWS.items():
        got = scalar(cur, f"SELECT count(*) FROM {table}")
        assert got == expected, f"{table}: expected {expected} rows, found {got}"
    print("  [OK] " + ", ".join(f"{t}={n}" for t, n in EXPECTED_ROWS.items() if n))
    layers = dict(rows(cur, "SELECT layer, count(*) FROM reference_features GROUP BY layer"))
    assert layers == {"village": 4, "road": 3, "farmland": 3, "infrastructure": 4}, layers
    print(f"  [OK] reference_features by layer: {dict(sorted(layers.items()))}")

    # ------------------------------------------------------------ 3
    print("\n--- 3. Geometry columns, spatial indexes, foreign keys ---")
    geoms = rows(cur, """
        SELECT c.relname, a.attname, upper(format_type(a.atttypid, a.atttypmod))
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
          AND format_type(a.atttypid, a.atttypmod) LIKE 'geometry%'""")
    declared, srids = set(), set()
    for table, column, decl in geoms:                       # decl looks like GEOMETRY(MULTIPOLYGON,4326)
        gtype, srid = decl[decl.index("(") + 1: decl.rindex(")")].split(",")
        declared.add((table, column, gtype))
        srids.add(int(srid))
    assert declared == GEOMETRY_COLUMNS, f"geometry columns differ: {sorted(declared)}"
    assert srids == {4326}, f"every geometry column must use SRID 4326, found {srids}"


    print(f"  [OK] {len(geoms)} geometry columns, all SRID 4326, with the expected types")

    gist = {r[0] for r in rows(cur, "SELECT tablename FROM pg_indexes WHERE schemaname = 'public' "
                                    "AND position('using gist' in lower(indexdef)) > 0")}
    assert gist == {g[0] for g in GEOMETRY_COLUMNS}, f"GIST indexes on: {gist}"
    print(f"  [OK] spatial (GIST) index on each of the {len(gist)} tables with geometry")

    n_fk = scalar(cur, "SELECT count(*) FROM pg_constraint "
                       "WHERE contype = 'f' AND connamespace = 'public'::regnamespace")
    assert n_fk == 22, f"expected 22 foreign keys, found {n_fk}"
    print(f"  [OK] {n_fk} foreign keys")

    # ------------------------------------------------------------ 4
    print("\n--- 4. Relationships and spatial sanity on the sample data ---")
    n = scalar(cur, """SELECT count(*) FROM disaster_events e
                       JOIN satellite_images i ON i.event_id = e.event_id
                       JOIN flood_analysis  a ON a.image_id  = i.image_id
                       JOIN flood_zones     z ON z.analysis_id = a.analysis_id""")
    assert n == 3
    print("  [OK] event -> image -> analysis -> zones joins give 3 zones")

    zones = {t: (c, float(a)) for t, c, a in rows(
        cur, "SELECT zone_type, count(*), sum(area_km2) FROM flood_zones GROUP BY zone_type")}
    new_total, perm_total = (float(v) for v in rows(
        cur, "SELECT new_flood_area_km2, permanent_water_area_km2 FROM flood_analysis")[0])
    assert zones["new_flood"][0] == 2 and zones["permanent_water"][0] == 1
    for name, recorded in (("new_flood", new_total), ("permanent_water", perm_total)):
        measured = zones[name][1]
        assert abs(measured - recorded) / recorded < 0.02, f"{name}: PostGIS {measured} vs row {recorded}"
        print(f"  [OK] {name}: zones measure {measured:.4f} km2 in PostGIS, analysis row says {recorded:.4f}")

    hits = dict(rows(cur, """SELECT f.layer, count(DISTINCT f.feature_id)
                             FROM reference_features f JOIN flood_zones z ON ST_Intersects(f.geom, z.geom)
                             WHERE z.zone_type = 'new_flood' GROUP BY f.layer"""))
    assert hits == {"village": 2, "road": 2, "farmland": 2, "infrastructure": 1}, hits
    print(f"  [OK] features touching new-flood zones: {dict(sorted(hits.items()))} "
          "(hand-checked: Alpha+Beta, R1+R3, F1+F2, H1)")

    # ------------------------------------------------------------ 5
    print("\n--- 5. The database refuses bad data ---")
    analysis_id = scalar(cur, "SELECT analysis_id FROM flood_analysis LIMIT 1")
    image_id = scalar(cur, "SELECT image_id FROM satellite_images LIMIT 1")
    source_id = scalar(cur, "SELECT source_id FROM satellite_sources LIMIT 1")

    expect_fail(cur, "user with an invalid role",
                "INSERT INTO users (username, email, password_hash, role) VALUES ('x', 'x@example.com', 'h', 'hacker')",
                code=CHECK_VIOLATION, constraint="users_role_valid")
    expect_fail(cur, "duplicate username",
                "INSERT INTO users (username, email, password_hash) VALUES ('admin_demo', 'other@example.com', 'h')",
                code=UNIQUE_VIOLATION)
    expect_fail(cur, "event that ends before it starts",
                "INSERT INTO disaster_events (name, start_date, end_date) VALUES ('bad', '2026-02-01', '2026-01-01')",
                code=CHECK_VIOLATION, constraint="disaster_events_dates_valid")
    expect_fail(cur, "image pointing to a missing event",
                "INSERT INTO satellite_images (event_id, source_id, file_name, file_path, footprint) "
                "VALUES (999999, %s, 'x.tif', 'x', ST_MakeEnvelope(0, 0, 1, 1, 4326))",
                (source_id,), code=FK_VIOLATION)
    expect_fail(cur, "analysis: 'no baseline' but a new-flood area",
                "INSERT INTO flood_analysis (image_id, baseline_method, model_name, status, "
                "valid_area_km2, water_area_km2, new_flood_area_km2) VALUES (%s, 'none', 'm.pth', 'completed', 10, 5, 2)",
                (image_id,), code=CHECK_VIOLATION, constraint="flood_analysis_baseline_fields")
    expect_fail(cur, "analysis: permanent + new does not equal total water",
                "INSERT INTO flood_analysis (image_id, baseline_method, model_name, status, valid_area_km2, "
                "water_area_km2, permanent_water_area_km2, new_flood_area_km2) "
                "VALUES (%s, 'jrc', 'm.pth', 'completed', 10, 5, 1, 1)",
                (image_id,), code=CHECK_VIOLATION, constraint="flood_analysis_split_consistent")
    expect_fail(cur, "zone with a Point instead of a MultiPolygon",
                "INSERT INTO flood_zones (analysis_id, zone_type, poly_no, area_km2, geom) "
                "VALUES (%s, 'water', 1, 0, ST_SetSRID(ST_MakePoint(92.9, 26.6), 4326))", (analysis_id,))
    expect_fail(cur, "zone in the wrong coordinate system (SRID 3857)",
                "INSERT INTO flood_zones (analysis_id, zone_type, poly_no, area_km2, geom) "
                "VALUES (%s, 'water', 1, 0, ST_Multi(ST_MakeEnvelope(10, 10, 11, 11, 3857)))", (analysis_id,))
    expect_fail(cur, "zone with an invalid (self-intersecting) polygon",
                "INSERT INTO flood_zones (analysis_id, zone_type, poly_no, area_km2, geom) "
                "VALUES (%s, 'water', 2, 0, ST_GeomFromText('MULTIPOLYGON(((0 0, 1 1, 1 0, 0 1, 0 0)))', 4326))",
                (analysis_id,), code=CHECK_VIOLATION, constraint="flood_zones_geom_valid")
    expect_fail(cur, "duplicate zone number in one analysis",
                "INSERT INTO flood_zones (analysis_id, zone_type, poly_no, area_km2, geom) "
                "VALUES (%s, 'new_flood', 1, 0, ST_Multi(ST_MakeEnvelope(92.90, 26.50, 92.91, 26.51, 4326)))",
                (analysis_id,), code=UNIQUE_VIOLATION)
    expect_fail(cur, "a road stored as a Point",
                "INSERT INTO reference_features (layer, name, source, geom) "
                "VALUES ('road', 'bad', 'test', ST_SetSRID(ST_MakePoint(92.9, 26.6), 4326))",
                code=CHECK_VIOLATION, constraint="reference_features_geom_matches_layer")

    # ------------------------------------------------------------ 6
    print("\n--- 6. The four impact tables accept valid rows and reject bad ones ---")
    cur.execute("""INSERT INTO affected_villages (analysis_id, feature_id, zone_type, relation, distance_m)
                   SELECT %s, feature_id, 'new_flood', 'inside', 0 FROM reference_features
                   WHERE name = 'DEMO Village Alpha'""", (analysis_id,))
    cur.execute("""INSERT INTO affected_roads (analysis_id, feature_id, zone_type, flooded_length_km,
                                               flooded_pct, flooded_geom)
                   SELECT %s, feature_id, 'new_flood', 1.0, 50, ST_Multi(geom) FROM reference_features
                   WHERE name = 'DEMO Road R1'""", (analysis_id,))
    cur.execute("""INSERT INTO agricultural_areas (analysis_id, feature_id, zone_type, flooded_area_km2,
                                                   flooded_pct, flooded_geom)
                   SELECT %s, feature_id, 'new_flood', 0.1, 50, ST_Multi(geom) FROM reference_features
                   WHERE name = 'DEMO Field F1'""", (analysis_id,))
    cur.execute("""INSERT INTO critical_infrastructure (analysis_id, feature_id, zone_type, relation, distance_m)
                   SELECT %s, feature_id, 'new_flood', 'near', 249 FROM reference_features
                   WHERE name = 'DEMO School S1'""", (analysis_id,))
    for table in ("affected_villages", "affected_roads", "agricultural_areas", "critical_infrastructure"):
        assert scalar(cur, f"SELECT count(*) FROM {table}") == 1
    print("  [OK] one valid row accepted by each of the 4 impact tables")

    expect_fail(cur, "village marked 'inside' but 50 m away",
                "INSERT INTO affected_villages (analysis_id, feature_id, zone_type, relation, distance_m) "
                "SELECT %s, feature_id, 'new_flood', 'inside', 50 FROM reference_features "
                "WHERE name = 'DEMO Village Beta'",
                (analysis_id,), code=CHECK_VIOLATION, constraint="affected_villages_inside_distance")
    expect_fail(cur, "impact computed against permanent water",
                "INSERT INTO critical_infrastructure (analysis_id, feature_id, zone_type, relation) "
                "SELECT %s, feature_id, 'permanent_water', 'inside' FROM reference_features "
                "WHERE name = 'DEMO Hospital H1'",
                (analysis_id,), code=CHECK_VIOLATION, constraint="critical_infrastructure_zone_valid")

    # ------------------------------------------------------------ 7
    print("\n--- 7. Deleting an event removes everything that belongs to it ---")
    cur.execute("DELETE FROM disaster_events")
    for table in ("satellite_images", "flood_analysis", "flood_zones", "affected_villages",
                  "affected_roads", "agricultural_areas", "critical_infrastructure",
                  "flood_reports", "emergency_actions"):
        assert scalar(cur, f"SELECT count(*) FROM {table}") == 0, f"{table} still has rows"
    assert scalar(cur, "SELECT count(*) FROM reference_features") == 14
    assert scalar(cur, "SELECT count(*) FROM users") == 2
    assert scalar(cur, "SELECT count(*) FROM satellite_sources") == 2
    print("  [OK] images, analyses, zones, impact rows, reports and actions are gone;")
    print("       users, sources and reference features are untouched")

    rebuild(cur)
    conn.close()
    print("\n  Sample data reloaded into the test database so you can browse it in pgAdmin or psql.")
    print("\n" + SEP)
    print("  Schema tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
