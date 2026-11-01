"""
GeoFlood AI - Phase 21a: how much OpenStreetMap data exists around each dataset chip?

For every chip of one country (default India) this asks the public Overpass API how many
villages/hamlets, roads, farmland areas and facilities OpenStreetMap has inside the chip's box,
and saves the counts to ai/results/osm_coverage_<country>.csv.

Usage (project root, internet needed):
    python -m gis.osm_coverage               # all India chips (about 68)
    python -m gis.osm_coverage --limit 3     # quick trial
Safe to stop and restart: chips already in the CSV are skipped (use --refresh to redo them).

Map data (c) OpenStreetMap contributors, available under the Open Database Licence (ODbL).
"""

import argparse
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd
import rasterio

from ai.src import config

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "GeoFloodAI-college-project/1.0"
LAYERS = ("villages", "roads", "farmland", "facilities")
OUT_DIR = config.ROOT / "ai" / "results"

QUERY_TEMPLATE = """[out:json][timeout:60][bbox:{bbox}];
nwr["place"~"^(village|hamlet)$"]->.villages;
way["highway"]->.roads;
nwr["landuse"~"^(farmland|meadow|orchard|farmyard)$"]->.farmland;
nwr["amenity"~"^(hospital|clinic|school|college|police|fire_station|shelter)$"]->.facilities;
.villages out count;
.roads out count;
.farmland out count;
.facilities out count;
"""


def chip_bbox(tif_path):
    """(south, west, north, east) of a chip, rounded OUTWARD to 5 decimals so the box covers the chip."""
    with rasterio.open(tif_path) as src:
        b = src.bounds
    return (math.floor(b.bottom * 1e5) / 1e5, math.floor(b.left * 1e5) / 1e5,
            math.ceil(b.top * 1e5) / 1e5, math.ceil(b.right * 1e5) / 1e5)


def build_query(bbox):
    return QUERY_TEMPLATE.format(bbox=",".join(f"{v:.5f}" for v in bbox))


def parse_counts(response):
    """Read the four 'count' blocks of an Overpass answer (in query order). Raises ValueError if unusable."""
    remark = str(response.get("remark", ""))
    if "runtime error" in remark.lower():
        raise ValueError(f"Overpass reported a problem: {remark}")
    blocks = [e for e in response.get("elements", []) if e.get("type") == "count"]
    if len(blocks) != len(LAYERS):
        raise ValueError(f"expected {len(LAYERS)} count blocks, got {len(blocks)}")
    try:
        return {name: int(block["tags"]["total"]) for name, block in zip(LAYERS, blocks)}
    except (KeyError, TypeError, ValueError):
        raise ValueError("the count blocks have an unexpected format")


def fetch_counts(bbox, endpoint=DEFAULT_ENDPOINT, retries=4):
    """Ask Overpass for the four counts of one box, retrying a few times on errors or timeouts."""
    data = urllib.parse.urlencode({"data": build_query(bbox)}).encode()
    request = urllib.request.Request(endpoint, data=data, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return parse_counts(json.loads(response.read().decode("utf-8")))
        except (urllib.error.URLError, TimeoutError, ValueError) as err:    # includes HTTP 429/504, bad JSON
            last_error = err
            wait = 5 * attempt
            print(f"      attempt {attempt}/{retries} failed ({err}); waiting {wait} s")
            time.sleep(wait)
    raise RuntimeError(f"Gave up after {retries} attempts: {last_error}")


def rank(df):
    """Sort chips by how many of the four layers have data, then by the total number of features."""
    df = df.copy()
    df["layers_with_data"] = (df[list(LAYERS)] > 0).sum(axis=1)
    df["total_features"] = df[list(LAYERS)].sum(axis=1)
    return df.sort_values(["layers_with_data", "total_features"], ascending=False)


def main():
    p = argparse.ArgumentParser(description="Count OpenStreetMap features around dataset chips")
    p.add_argument("--country", default="India")
    p.add_argument("--limit", type=int, default=0, help="only the first N chips (for a quick trial)")
    p.add_argument("--delay", type=float, default=2.0, help="seconds to pause between requests")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    p.add_argument("--refresh", action="store_true", help="ignore the saved CSV and start again")
    args = p.parse_args()

    stats_path = config.PROCESSED / "chip_stats.csv"
    if not stats_path.exists():
        raise SystemExit(f"{stats_path} not found. Run: python -m ai.src.explore_dataset")
    chips = pd.read_csv(stats_path)
    chips = chips[chips.country == args.country].sort_values("chip")
    if args.limit:
        chips = chips.head(args.limit)
    if chips.empty:
        raise SystemExit(f"No chips found for country '{args.country}'.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / f"osm_coverage_{args.country.lower()}.csv"
    rows, done = [], set()
    if out_csv.exists() and not args.refresh:
        saved = pd.read_csv(out_csv)
        rows, done = saved.to_dict("records"), set(saved.chip)
        print(f"Resuming: {len(done)} chips already in {out_csv.name}")

    print(f"\nScanning {len(chips)} {args.country} chips on {args.endpoint}\n")
    for i, r in enumerate(chips.itertuples(), start=1):
        if r.chip in done:
            continue
        south, west, north, east = chip_bbox(config.IMG_DIR / f"{r.chip}_S1Hand.tif")
        counts = fetch_counts((south, west, north, east), args.endpoint)
        rows.append({"chip": r.chip, "split": r.split, "label_water_pct": round(r.flood_pct, 1),
                     "south": south, "west": west, "north": north, "east": east, **counts})
        pd.DataFrame(rows).to_csv(out_csv, index=False)               # saved after every chip
        print(f"  [{i:>3}/{len(chips)}] {r.chip:<16} villages {counts['villages']:>3}  roads {counts['roads']:>4}  "
              f"farmland {counts['farmland']:>3}  facilities {counts['facilities']:>3}")
        time.sleep(args.delay)

    df = rank(pd.DataFrame(rows))
    show = ["chip", "split", "label_water_pct", *LAYERS, "layers_with_data", "total_features"]
    print(f"\n--- Best {min(15, len(df))} chips (most layers with data first) ---")
    print(df[show].head(15).to_string(index=False))
    print(f"\n--- Over all {len(df)} chips scanned ---")
    for layer in LAYERS:
        print(f"  chips with at least one {layer[:-1] if layer.endswith('s') else layer:<10}: "
              f"{int((df[layer] > 0).sum()):>3}   (median count {df[layer].median():.0f})")
    print(f"  chips with ALL four layers non-empty: {int((df.layers_with_data == 4).sum())}")
    print(f"\nSaved: {out_csv}")
    print("Map data (c) OpenStreetMap contributors (ODbL)")


if __name__ == "__main__":
    main()
