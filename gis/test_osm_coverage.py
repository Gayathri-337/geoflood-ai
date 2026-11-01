"""
GeoFlood AI - Phase 21a test for gis/osm_coverage.py. Works offline (no internet needed).

Usage (project root):  python -m gis.test_osm_coverage
"""

import json
import urllib.error
import urllib.request

import pandas as pd
import rasterio

from ai.src import config
from gis import osm_coverage as osm

SEP = "=" * 70

# The real answer Overpass gave for the India_591317 box (from your Overpass Turbo output)
REAL_RESPONSE = {
    "version": 0.6,
    "generator": "Overpass API 0.7.62.4 2390de5a",
    "elements": [
        {"type": "count", "id": 0, "tags": {"nodes": "1", "ways": "0", "relations": "0", "total": "1"}},
        {"type": "count", "id": 0, "tags": {"nodes": "0", "ways": "16", "relations": "0", "total": "16"}},
        {"type": "count", "id": 0, "tags": {"nodes": "0", "ways": "0", "relations": "0", "total": "0"}},
        {"type": "count", "id": 0, "tags": {"nodes": "0", "ways": "0", "relations": "0", "total": "0"}},
    ],
}
EXPECTED = {"villages": 1, "roads": 16, "farmland": 0, "facilities": 0}


def ok(message):
    print(f"  [OK] {message}")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_parse():
    assert osm.parse_counts(REAL_RESPONSE) == EXPECTED
    ok("the real Overpass answer for India_591317 is read as villages 1, roads 16, farmland 0, facilities 0")
    bad = {
        "a runtime-error remark": {"remark": 'runtime error: Query timed out in "query" at line 6 after 61 seconds.',
                                   "elements": REAL_RESPONSE["elements"]},
        "too few count blocks": {"elements": REAL_RESPONSE["elements"][:3]},
        "no elements at all": {},
        "a non-numeric total": {"elements": [{"type": "count", "tags": {"total": "many"}}] * 4},
        "blocks without tags": {"elements": [{"type": "count"}] * 4},
    }
    for label, response in bad.items():
        try:
            osm.parse_counts(response)
        except ValueError:
            continue
        raise AssertionError(f"{label} should have been rejected")
    ok(f"{len(bad)} unusable answers are rejected: " + ", ".join(bad))


def test_bbox():
    tif = config.IMG_DIR / "India_591317_S1Hand.tif"
    south, west, north, east = osm.chip_bbox(tif)
    with rasterio.open(tif) as src:
        b = src.bounds
    assert south <= b.bottom and west <= b.left and north >= b.top and east >= b.right
    assert max(b.bottom - south, b.left - west, north - b.top, east - b.right) < 2e-5
    ok(f"the box ({south}, {west}, {north}, {east}) covers the chip and is rounded outward by under 0.00002 degrees")
    query = osm.build_query((south, west, north, east))
    assert query.count("out count;") == 4
    assert f"[bbox:{south:.5f},{west:.5f},{north:.5f},{east:.5f}]" in query
    ok("the query contains the box (south, west, north, east) and four count outputs")


def test_rank():
    df = pd.DataFrame([
        {"chip": "a", "villages": 1, "roads": 16, "farmland": 0, "facilities": 0},
        {"chip": "b", "villages": 3, "roads": 5, "farmland": 2, "facilities": 1},
        {"chip": "c", "villages": 0, "roads": 40, "farmland": 0, "facilities": 0},
        {"chip": "d", "villages": 2, "roads": 2, "farmland": 1, "facilities": 1},
    ])
    assert list(osm.rank(df).chip) == ["b", "d", "a", "c"]
    ok("ranking: chips with more non-empty layers come first, then more features (b, d, a, c)")


def test_retry():
    calls = {"n": 0}

    def flaky(request, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("temporary failure")
        return FakeResponse(REAL_RESPONSE)

    def always_down(request, timeout=None):
        calls["n"] += 1
        raise urllib.error.URLError("down")

    real_urlopen, real_sleep = urllib.request.urlopen, osm.time.sleep
    osm.time.sleep = lambda seconds: None            # do not really wait during the test
    try:
        urllib.request.urlopen = flaky
        assert osm.fetch_counts((26.58, 92.9, 26.63, 92.95), "http://example.invalid") == EXPECTED
        assert calls["n"] == 3
        ok("two temporary failures are retried; the third attempt succeeds")

        calls["n"] = 0
        urllib.request.urlopen = always_down
        try:
            osm.fetch_counts((26.58, 92.9, 26.63, 92.95), "http://example.invalid", retries=3)
        except RuntimeError as err:
            assert "Gave up after 3 attempts" in str(err) and calls["n"] == 3
        else:
            raise AssertionError("a permanently failing server should end in an error")
        ok("a server that stays down ends in a clear error after the allowed number of attempts")
    finally:
        urllib.request.urlopen, osm.time.sleep = real_urlopen, real_sleep


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 21a OSM Coverage Scan: offline test")
    print(SEP)
    print()
    test_parse()
    test_bbox()
    test_rank()
    test_retry()
    print("\n" + SEP)
    print("  OSM coverage tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
