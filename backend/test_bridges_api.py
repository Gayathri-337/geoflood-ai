"""
GeoFlood AI - Phase 21c test: roads on bridges are shown but not counted as flooded roads.

DESTRUCTIVE: rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m backend.test_bridges_api
"""

import json
import os

import psycopg2
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai.src import config
from backend.database import get_db
from backend.main import app
from backend.security import access_policy

DB_DIR = config.ROOT / "database"
SEP = "=" * 70
BUILD_FILES = ("reset.sql", "schema.sql", "impact_analysis.sql", "sample_data.sql")


def ok(message):
    print(f"  [OK] {message}")


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 21c Bridges Test")
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

    app.dependency_overrides[get_db] = use_test_db
    app.dependency_overrides[access_policy] = lambda: None
    client = TestClient(app)
    base = f"/api/analyses/{aid}"

    def summary():
        r = client.get(f"{base}/impact")
        assert r.status_code == 200, r.text
        return r.json()

    def roads_layer():
        r = client.get(f"{base}/impact/roads")
        assert r.status_code == 200, r.text
        return {f["properties"]["name"]: f["properties"] for f in r.json()["features"]}

    def run():
        r = client.post(f"{base}/impact")
        assert r.status_code == 200, r.text
        return r.json()

    def tag(name, tags):
        """Give a road the stored-properties shape that gis/osm_features.py produces."""
        cur.execute("UPDATE reference_features SET properties = %s::jsonb WHERE name = %s",
                    (json.dumps({"osm_id": "way/0", "tags": tags}), name))

    # ------------------------------------------------------------ 1
    print("\n--- 1. Without any bridge nothing changes ---")
    r = run()
    assert (r["villages"], r["roads"], r["farmland"], r["infrastructure"], r["bridges"]) == (2, 2, 2, 3, 0), r
    s = summary()
    assert s["roads"]["count"] == 2 and 1.545 <= s["roads"]["flooded_length_km"] <= 1.555
    assert s["roads"]["bridges"] == {"count": 0, "length_km": 0}
    layer = roads_layer()
    assert set(layer) == {"DEMO Road R1", "DEMO Road R3"} and all(p["on_bridge"] is False for p in layer.values())
    ok("2 flooded roads, 1.55 km, 0 bridges; every road feature has on_bridge = false")

    # ------------------------------------------------------------ 2
    print("\n--- 2. One road tagged bridge=yes ---")
    tag("DEMO Road R3", {"bridge": "yes", "highway": "trunk"})
    s = summary()                                         # read straight from the stored rows, no recompute
    assert s["roads"]["count"] == 1 and 0.990 <= s["roads"]["flooded_length_km"] <= 1.002, s["roads"]
    assert s["roads"]["bridges"]["count"] == 1 and 0.548 <= s["roads"]["bridges"]["length_km"] <= 0.560
    ok(f"summary: {s['roads']['count']} flooded road ({s['roads']['flooded_length_km']:.3f} km) and "
       f"{s['roads']['bridges']['count']} bridge ({s['roads']['bridges']['length_km']:.3f} km)")
    assert scalar(cur, "SELECT count(*) FROM affected_roads WHERE analysis_id = %s", (aid,)) == 2
    ok("the bridge is still stored: affected_roads keeps both rows")
    layer = roads_layer()
    assert layer["DEMO Road R3"]["on_bridge"] is True and layer["DEMO Road R1"]["on_bridge"] is False
    ok("the roads layer marks R3 as on_bridge = true and R1 as false")
    r = run()
    assert (r["villages"], r["roads"], r["farmland"], r["infrastructure"], r["bridges"]) == (2, 1, 2, 3, 1), r
    ok("POST /impact reports roads 1 and bridges 1; the other layers are unchanged (2 / 2 / 3)")

    # ------------------------------------------------------------ 3
    print("\n--- 3. Which tag values count as a bridge ---")
    cases = [({"bridge": "yes"}, 1), ({"bridge": "viaduct"}, 1), ({"bridge": "movable"}, 1),
             ({"bridge": "no"}, 0), ({"bridge": ""}, 0), ({"highway": "trunk"}, 0)]
    for tags, expected in cases:
        tag("DEMO Road R3", tags)
        assert summary()["roads"]["bridges"]["count"] == expected, tags
    cur.execute("UPDATE reference_features SET properties = '{}'::jsonb WHERE name = 'DEMO Road R3'")
    assert summary()["roads"]["bridges"]["count"] == 0
    ok("bridge=yes, viaduct and movable count; bridge=no, an empty value, no bridge tag and no tags at all do not")

    # ------------------------------------------------------------ 4
    print("\n--- 4. Every affected road on a bridge ---")
    tag("DEMO Road R1", {"bridge": "yes"})
    tag("DEMO Road R3", {"bridge": "yes"})
    s = summary()
    assert s["roads"]["count"] == 0 and s["roads"]["flooded_length_km"] == 0
    assert s["roads"]["bridges"]["count"] == 2 and 1.545 <= s["roads"]["bridges"]["length_km"] <= 1.555
    r = run()
    assert r["roads"] == 0 and r["bridges"] == 2, r
    ok("0 flooded roads and 0 km, 2 bridges; the roads count never goes negative")

    # ------------------------------------------------------------ 5
    print("\n--- 5. Everything else is untouched ---")
    s = summary()
    assert s["villages"]["count"] == 2 and s["farmland"]["count"] == 2 and s["infrastructure"]["count"] == 3
    assert client.get("/api/stats/dashboard").status_code == 200
    ok("villages 2, farmland 2, infrastructure 3, and the dashboard statistics still work")

    app.dependency_overrides.clear()
    engine.dispose()
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())
    conn.close()
    print("\n  Test database reset to the sample data.")
    print("\n" + SEP)
    print("  Bridge tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
