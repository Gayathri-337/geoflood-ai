import json
import time
import urllib.parse
import urllib.request
import urllib.error
import pandas as pd

INPUT = "ai/results/predictions/test/summary.csv"
OUTPUT = "ai/results/osm_coverage.csv"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

df = pd.read_csv(INPUT)

results = []

def get_count(element):
    tags = element.get("tags", {})
    return sum(int(tags.get(k, 0)) for k in
               ("nodes", "ways", "relations"))

for index, row in df.iterrows():
    chip = row["chip"]
    lat = float(row["lat"])
    lon = float(row["lon"])
    # Approximate chip coverage: fixed +/- 0.023 degrees around its centre.
    # This is not an exact geographic representation of the chip boundary.
    south = lat - 0.023
    west = lon - 0.023
    north = lat + 0.023
    east = lon + 0.023

    bbox = f"({south},{west},{north},{east})"

    query = f"""
    [out:json][timeout:60];
    nwr["place"~"^(village|hamlet)$"]{bbox}->.villages;
    .villages out count;

    way["highway"]{bbox}->.roads;
    .roads out count;

    nwr["landuse"~"^(farmland|meadow|orchard|farmyard)$"]{bbox}->.farmland;
    .farmland out count;

    nwr["amenity"~"^(hospital|clinic|school|college|police|fire_station|shelter)$"]{bbox}->.facilities;
    .facilities out count;
    """

    print(f"\n[{index + 1}/{len(df)}] Scanning {chip}...")

    counts = [0, 0, 0, 0]
    status = "OK"
    error_message = ""

    for attempt in range(3):
        try:
            data = urllib.parse.urlencode({"data": query}).encode()
            request = urllib.request.Request(
                OVERPASS_URL,
                data=data,
                headers={"User-Agent": "GeoFloodAI/1.0"}
            )

            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode())

            elements = [
                e for e in payload.get("elements", [])
                if e.get("type") == "count"
            ]

            if len(elements) != 4:
                raise ValueError("Expected 4 count results from Overpass")

            counts = [get_count(e) for e in elements]
            break

        except Exception as exc:
            error_message = str(exc)
            print(f"  Attempt {attempt + 1} failed: {error_message}")

            if attempt < 2:
                time.sleep(10 * (attempt + 1))
            else:
                status = "ERROR"

    villages, roads, farmland, facilities = counts

    coverage_categories = sum(
        count > 0 for count in counts
    )

    results.append({
        "chip": chip,
        "lat": lat,
        "lon": lon,
        "south": south,
        "west": west,
        "north": north,
        "east": east,
        "water_pct": row["water_pct"],
        "villages": villages,
        "roads": roads,
        "farmland": farmland,
        "facilities": facilities,
        "coverage_categories": coverage_categories,
        "status": status,
        "error": error_message
    })

    print(
        f"  Villages: {villages} | Roads: {roads} | "
        f"Farmland: {farmland} | Facilities: {facilities}"
    )

    if index < len(df) - 1:
        time.sleep(3)

result_df = pd.DataFrame(results)

result_df = result_df.sort_values(
    by=[
        "coverage_categories",
        "villages",
        "facilities",
        "farmland",
        "roads"
    ],
    ascending=False
)

result_df.insert(
    0, "rank", range(1, len(result_df) + 1)
)

result_df.to_csv(OUTPUT, index=False)

print("\n" + "=" * 75)
print("OSM COVERAGE RANKING")
print("=" * 75)

print(result_df[
    [
        "rank", "chip", "villages", "roads",
        "farmland", "facilities", "coverage_categories", "status"
    ]
].to_string(index=False))

print(f"\nResults saved to: {OUTPUT}")
print("\nOnly rows with status OK should be used for ranking.")
