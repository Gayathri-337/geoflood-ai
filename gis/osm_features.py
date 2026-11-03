"""
GeoFlood AI - Phase 21b: download OpenStreetMap features around chips and load them into PostGIS.

    python -m gis.osm_features --dry-run          # download, convert, write GeoJSON; database untouched
    python -m gis.osm_features --from-cache       # load into the real database (uses the saved downloads)
    python -m gis.osm_features --chips India_828067 --margin-m 600

For each chip: the chip's box plus a margin is sent to the Overpass API; the answer (cached in
ai/data/raw/osm/) is converted to shapes and stored in the reference_features table.
Elements are put in ONE layer: place -> village, amenity -> infrastructure, highway -> road,
landuse -> farmland. Multipolygon relations are skipped (and counted).

Map data (c) OpenStreetMap contributors, available under the Open Database Licence (ODbL).
"""

import argparse
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

from dotenv import load_dotenv
from shapely import make_valid
from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.ops import unary_union
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ai.src import config
from gis.osm_coverage import DEFAULT_ENDPOINT, USER_AGENT, chip_bbox

SOURCE = "openstreetmap"
RAW_OSM_DIR = config.ROOT / "ai" / "data" / "raw" / "osm"
EXPORT_DIR = config.ROOT / "ai" / "results" / "osm_features"
DEFAULT_CHIPS = ("India_828067", "India_747992", "India_1018327", "India_591317")

PLACES = {"village", "hamlet"}
AMENITIES = {"hospital", "clinic", "school", "college", "police", "fire_station", "shelter"}
LANDUSES = {"farmland", "meadow", "orchard", "farmyard"}
KEPT_TAGS = ("name", "name:en", "ref", "highway", "place", "landuse", "amenity", "bridge", "surface", "population")

QUERY_TEMPLATE = """[out:json][timeout:120][bbox:{bbox}];
(
  nwr["place"~"^({places})$"];
  way["highway"];
  nwr["landuse"~"^({landuses})$"];
  nwr["amenity"~"^({amenities})$"];
);
out geom;
"""

INSERT_SQL = text(f"""
INSERT INTO reference_features (layer, name, category, source, source_ref, properties, geom)
VALUES (:layer, :name, :category, '{SOURCE}', :source_ref, CAST(:properties AS jsonb),
        ST_GeomFromWKB(:wkb, 4326))
ON CONFLICT (layer, source, source_ref) DO UPDATE
   SET name = EXCLUDED.name, category = EXCLUDED.category, properties = EXCLUDED.properties,
       geom = EXCLUDED.geom, loaded_at = now()
""")


# ------------------------------------------------------------------ the query
def expand_bbox(bbox, margin_m):
    """Grow a (south, west, north, east) box by margin_m metres on every side."""
    south, west, north, east = bbox
    dlat = margin_m / 111_320.0
    dlon = margin_m / (111_320.0 * math.cos(math.radians((south + north) / 2)))
    return (round(south - dlat, 5), round(west - dlon, 5), round(north + dlat, 5), round(east + dlon, 5))


def build_query(bbox):
    return QUERY_TEMPLATE.format(
        bbox=",".join(f"{v:.5f}" for v in bbox),
        places="|".join(sorted(PLACES)), landuses="|".join(sorted(LANDUSES)),
        amenities="|".join(sorted(AMENITIES)))


def check_response(payload):
    """Raise ValueError if an Overpass answer is unusable."""
    remark = str(payload.get("remark", ""))
    if "runtime error" in remark.lower():
        raise ValueError(f"Overpass reported a problem: {remark}")
    if not isinstance(payload.get("elements"), list):
        raise ValueError("the answer has no 'elements' list")


def run_query(query, endpoint=DEFAULT_ENDPOINT, retries=4):
    """Send a query to Overpass, retrying a few times on errors or timeouts."""
    data = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(endpoint, data=data, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
            check_response(payload)
            return payload
        except (urllib.error.URLError, TimeoutError, ValueError) as err:     # includes HTTP 502/504 and bad JSON
            last_error = err
            wait = 5 * attempt
            print(f"      attempt {attempt}/{retries} failed ({err}); waiting {wait} s")
            time.sleep(wait)
    raise RuntimeError(f"Gave up after {retries} attempts: {last_error}")


# ------------------------------------------------------------------ elements -> shapes
def classify(tags):
    """(layer, category) of an element; the first matching rule wins. (None, None) if it fits no layer."""
    if tags.get("place") in PLACES:
        return "village", tags["place"]
    if tags.get("amenity") in AMENITIES:
        return "infrastructure", tags["amenity"]
    if "highway" in tags:
        return "road", tags["highway"]
    if tags.get("landuse") in LANDUSES:
        return "farmland", tags["landuse"]
    return None, None


def polygonal_part(geom):
    """The polygon part of a geometry (a repaired polygon may come back as a collection), or None."""
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    if geom.geom_type == "GeometryCollection":
        parts = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty]
        if parts:
            return unary_union(parts)
    return None


def build_geometry(layer, element, skipped):
    """Shapely geometry (longitude, latitude) for one node or way, or None with the reason counted."""
    if element["type"] == "node":
        if layer in ("village", "infrastructure"):
            return Point(element["lon"], element["lat"])
        skipped["node_not_usable"] += 1
        return None

    coords = [(p["lon"], p["lat"]) for p in (element.get("geometry") or []) if p]
    if layer == "road":
        if len(set(coords)) < 2:
            skipped["too_few_points"] += 1
            return None
        return LineString(coords)

    if len(coords) < 4 or coords[0] != coords[-1]:
        skipped["not_a_closed_area"] += 1
        return None
    polygon = Polygon(coords)
    if not polygon.is_valid:
        polygon = make_valid(polygon)
    area = polygonal_part(polygon)
    if area is None:
        skipped["invalid_geometry"] += 1
    return area


def parse_elements(payload):
    """Convert an Overpass answer into feature dicts. Returns (features, Counter of skipped elements)."""
    skipped, features, seen = Counter(), [], set()
    timestamp = (payload.get("osm3s") or {}).get("timestamp_osm_base")

    for element in payload.get("elements", []):
        kind, osm_id = element.get("type"), element.get("id")
        if kind not in ("node", "way", "relation") or osm_id is None:
            skipped["unreadable_element"] += 1
            continue
        if (kind, osm_id) in seen:
            skipped["duplicate"] += 1
            continue
        seen.add((kind, osm_id))
        if kind == "relation":
            skipped["relations"] += 1
            continue

        tags = element.get("tags") or {}
        layer, category = classify(tags)
        if layer is None:
            skipped["unclassified"] += 1
            continue
        try:
            geom = build_geometry(layer, element, skipped)
        except (KeyError, TypeError, ValueError):
            skipped["unreadable_element"] += 1
            continue
        if geom is None:
            continue

        ref = f"{kind}/{osm_id}"
        name = (tags.get("name") or tags.get("name:en") or "").strip()[:200] or None
        features.append({
            "layer": layer, "name": name, "category": str(category)[:50], "source_ref": ref,
            "properties": {"osm_id": ref,
                           "tags": {k: str(tags[k])[:200] for k in KEPT_TAGS if k in tags},
                           "osm_data_timestamp": timestamp},
            "geom": geom,
        })
    return features, skipped


def to_geojson(features):
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": mapping(f["geom"]),
        "properties": {"layer": f["layer"], "name": f["name"], "category": f["category"],
                       "source_ref": f["source_ref"]}} for f in features]}


# ------------------------------------------------------------------ database
def load_features(db, features):
    """Insert or update features in reference_features. Does NOT commit. Returns the number of rows written."""
    rows = [{"layer": f["layer"], "name": f["name"], "category": f["category"], "source_ref": f["source_ref"],
             "properties": json.dumps(f["properties"]), "wkb": f["geom"].wkb} for f in features]
    for start in range(0, len(rows), 500):
        db.execute(INSERT_SQL, rows[start:start + 500])
    return len(rows)


# ------------------------------------------------------------------ command line
def main():
    p = argparse.ArgumentParser(description="Download OpenStreetMap features around chips and load them into PostGIS")
    p.add_argument("--chips", nargs="+", default=list(DEFAULT_CHIPS))
    p.add_argument("--margin-m", type=float, default=600, help="metres added around each chip's box")
    p.add_argument("--from-cache", action="store_true", help="use saved downloads instead of asking Overpass")
    p.add_argument("--dry-run", action="store_true", help="do not touch the database")
    p.add_argument("--database", choices=("main", "test"), default="main")
    p.add_argument("--delay", type=float, default=2.0, help="seconds to pause between downloads")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    args = p.parse_args()

    session = None
    if not args.dry_run:
        load_dotenv(config.ROOT / ".env")
        url = os.getenv("DATABASE_URL" if args.database == "main" else "TEST_DATABASE_URL")
        if not url:
            raise SystemExit("The database URL is missing from .env.")
        engine = create_engine(url, pool_pre_ping=True)
        session = Session(engine)
        print(f"Loading into database: {engine.url.database}")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    totals = Counter()
    for i, chip in enumerate(args.chips, start=1):
        tif = config.IMG_DIR / f"{chip}_S1Hand.tif"
        if not tif.exists():
            raise SystemExit(f"Chip not found: {tif}")
        box = expand_bbox(chip_bbox(tif), args.margin_m)
        cache = RAW_OSM_DIR / f"{chip}.json"

        print(f"\n[{i}/{len(args.chips)}] {chip}   box {box}  (chip + {args.margin_m:.0f} m)")
        if args.from_cache and cache.exists():
            payload = json.loads(cache.read_text())
            check_response(payload)
            print("      loaded from the saved download")
        else:
            payload = run_query(build_query(box), args.endpoint)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(payload))
            print(f"      downloaded and saved to {cache.relative_to(config.ROOT)}")
            time.sleep(args.delay)

        features, skipped = parse_elements(payload)
        counts = Counter(f["layer"] for f in features)
        totals.update(counts)
        print(f"      OSM data timestamp: {(payload.get('osm3s') or {}).get('timestamp_osm_base')}")
        print("      " + ", ".join(f"{layer} {counts.get(layer, 0)}"
                                   for layer in ("village", "road", "farmland", "infrastructure")))
        roads = Counter(f["category"] for f in features if f["layer"] == "road")
        print(f"      road classes: {dict(roads.most_common(8))}")
        print(f"      skipped: {dict(skipped)}")

        out = EXPORT_DIR / f"{chip}_osm_features.geojson"
        out.write_text(json.dumps(to_geojson(features)))
        print(f"      GeoJSON for QGIS: {out.relative_to(config.ROOT)}")

        if session is not None:
            try:
                written = load_features(session, features)
                session.commit()
            except Exception:
                session.rollback()
                raise
            print(f"      stored {written} features in reference_features")

    print("\nDone. Totals over all chips:", dict(totals))
    print("Map data (c) OpenStreetMap contributors (ODbL)")


if __name__ == "__main__":
    main()
