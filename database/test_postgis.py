"""
GeoFlood AI - Phase 13 test: PostgreSQL + PostGIS.

Checks the connection, the PostGIS version and coordinate transformation, then runs a real
spatial workflow with the water polygons of India_591317 from Phase 11: insert, spatial
index, area (spheroid and UTM), an intersection query, and a read-back with GeoPandas.
The scratch table is deleted at the end.

Usage (project root):  python -m database.test_postgis
"""

import os

import geopandas as gpd
import psycopg2
from dotenv import load_dotenv
from shapely.geometry import box

from ai.src import config
from gis.area_calculator import polygon_area_km2

SEP = "=" * 66
TABLE = "phase13_test_polygons"
GEOJSON = config.ROOT / "ai" / "results" / "polygons" / "India_591317.geojson"


def rel_diff(a, b):
    return abs(a - b) / b


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 13 PostgreSQL / PostGIS Test")
    print(SEP)

    load_dotenv(config.ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not found. Create the .env file (Step 13.5).")
    if not GEOJSON.exists():
        raise SystemExit(f"{GEOJSON} not found. Run: python -m gis.test_polygons")

    try:
        conn = psycopg2.connect(url, connect_timeout=5)
    except psycopg2.OperationalError as err:
        raise SystemExit(f"\nCould not connect:\n{err}\nSee the error table in the instructions.")
    conn.autocommit = True
    cur = conn.cursor()

    print("\n--- 1. Connection and PostGIS ---")
    cur.execute("SELECT current_user, current_database(), split_part(version(), ',', 1)")
    user, db, version = cur.fetchone()
    print(f"  [OK] connected as '{user}' to database '{db}'")
    print(f"       {version}")
    cur.execute("SELECT PostGIS_Version()")
    print(f"  [OK] PostGIS {cur.fetchone()[0]}")

    cur.execute("SELECT ST_X(p), ST_Y(p) FROM "
                "(SELECT ST_Transform(ST_SetSRID(ST_MakePoint(92.9, 26.6), 4326), 32646) AS p) t")
    x, y = cur.fetchone()
    assert 480_000 < x < 500_000 and 2_900_000 < y < 3_000_000, f"unexpected UTM coordinates {x}, {y}"
    print(f"  [OK] coordinate transformation works: (92.9E, 26.6N) -> UTM 46N ({x:,.0f}, {y:,.0f})")

    print("\n--- 2. Real polygons from Phase 11 ---")
    gdf = gpd.read_file(GEOJSON)
    expected_km2 = polygon_area_km2(gdf)                 # GeoPandas, local UTM zone
    minx, miny, maxx, maxy = (float(v) for v in gdf.total_bounds)
    midx = (minx + maxx) / 2
    expected_half = int(gdf.intersects(box(minx, miny, midx, maxy)).sum())
    print(f"  GeoJSON: {len(gdf)} polygons, {expected_km2:.3f} km2 (GeoPandas, UTM)")

    try:
        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
        cur.execute(f"""
            CREATE TABLE {TABLE} (
                id        SERIAL PRIMARY KEY,
                poly_id   INTEGER,
                n_pixels  INTEGER,
                mean_prob REAL,
                geom      geometry(MultiPolygon, 4326) NOT NULL
            )""")
        cur.execute(f"CREATE INDEX {TABLE}_geom_idx ON {TABLE} USING GIST (geom)")
        for row in gdf.itertuples():
            cur.execute(
                f"INSERT INTO {TABLE} (poly_id, n_pixels, mean_prob, geom) "
                "VALUES (%s, %s, %s, ST_Multi(ST_GeomFromWKB(%s, 4326)))",
                (int(row.poly_id), int(row.n_pixels), float(row.mean_prob),
                 psycopg2.Binary(row.geometry.wkb)))

        cur.execute(f"SELECT count(*) FROM {TABLE}")
        assert cur.fetchone()[0] == len(gdf)
        print(f"  [OK] inserted and counted {len(gdf)} polygons; GIST spatial index created")

        cur.execute(f"SELECT sum(ST_Area(geom::geography)) / 1e6, "
                    f"sum(ST_Area(ST_Transform(geom, 32646))) / 1e6 FROM {TABLE}")
        geo_km2, utm_km2 = (float(v) for v in cur.fetchone())
        assert rel_diff(utm_km2, expected_km2) < 0.005 and rel_diff(geo_km2, expected_km2) < 0.005
        print(f"  [OK] area in PostGIS: {geo_km2:.3f} km2 on the spheroid, {utm_km2:.3f} km2 in UTM 46N "
              f"(GeoPandas: {expected_km2:.3f})")

        cur.execute(f"SELECT count(*) FROM {TABLE} "
                    "WHERE ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))",
                    (minx, miny, midx, maxy))
        got = cur.fetchone()[0]
        assert got == expected_half, f"PostGIS found {got}, GeoPandas found {expected_half}"
        print(f"  [OK] ST_Intersects with the west half of the chip: {got} polygons "
              f"(same as GeoPandas)")

        print("\n--- 3. Read back with GeoPandas + SQLAlchemy (the backend will use this) ---")
        try:
            from sqlalchemy import create_engine
            engine = create_engine(url)
            back = gpd.read_postgis(f"SELECT poly_id, n_pixels, geom FROM {TABLE}", engine,
                                    geom_col="geom")
            assert len(back) == len(gdf) and back.crs is not None and back.crs.to_epsg() == 4326
            print(f"  [OK] read {len(back)} polygons back, CRS EPSG:{back.crs.to_epsg()}")
            engine.dispose()
        except Exception as err:
            print(f"  [FAIL] {type(err).__name__}: {err}")
            print("         Send me this message. The database itself is fine if parts 1 and 2 passed.")
    finally:
        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
        conn.close()
        print(f"\n  Scratch table {TABLE} removed.")

    print("\n" + SEP)
    print("  PostGIS tests finished.")
    print(SEP)


if __name__ == "__main__":
    main()
