"""
GeoFlood AI - Phase 30 test: the reference-data coverage message (no database, no server needed).

Usage (project root):  python -m backend.test_coverage
"""

from backend.services.coverage import describe_coverage

SEP = "=" * 70


def ok(message):
    print(f"  [OK] {message}")


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 30 Reference Coverage Test")
    print(SEP)

    print("\n--- 1. Nothing stored inside the image ---")
    c = describe_coverage({"villages": 0, "roads": 0, "farmland": 0, "infrastructure": 0})
    assert c["level"] == "none" and c["empty_layers"] == ["villages", "roads", "farmland", "infrastructure"]
    assert "no data for this area" in c["message"] and "not that nothing was affected" in c["message"]
    assert c["counts"] == {"villages": 0, "roads": 0, "farmland": 0, "infrastructure": 0}
    ok("level 'none': an impact of 0 is explained as 'no data', not 'nothing affected'")

    print("\n--- 2. Some layers empty ---")
    c = describe_coverage({"villages": 1, "roads": 10, "farmland": 0, "infrastructure": 0})
    assert c["level"] == "partial" and c["empty_layers"] == ["farmland", "infrastructure"]
    assert "no farmland and facilities inside this image" in c["message"] and "lower bounds" in c["message"]
    c = describe_coverage({"villages": 0, "roads": 5, "farmland": 2, "infrastructure": 1})
    assert c["level"] == "partial" and "no villages inside this image" in c["message"]
    c = describe_coverage({"villages": 1, "roads": 0, "farmland": 0, "infrastructure": 3})
    assert "no roads and farmland inside" in c["message"]
    c = describe_coverage({"villages": 4, "roads": 9, "farmland": 0, "infrastructure": 2})
    assert "no farmland inside" in c["message"]
    ok("level 'partial': the empty layers are named with correct grammar")

    print("\n--- 3. Every layer has data ---")
    c = describe_coverage({"villages": 1, "roads": 104, "farmland": 1, "infrastructure": 3})
    assert c["level"] == "ok" and c["empty_layers"] == []
    assert c["message"].startswith("Reference data inside this image: 1 village, 104 road segments, 1 farmland area "
                                   "and 3 facilities.")
    assert "lower bounds" in c["message"]
    ok("level 'ok': counts with singular and plural words, still reminding that figures are lower bounds")

    print("\n--- 4. Bad input never becomes a wrong claim ---")
    assert describe_coverage(None)["level"] == "none"
    assert describe_coverage({})["level"] == "none"
    c = describe_coverage({"villages": "3", "roads": -4, "farmland": None, "infrastructure": "x"})
    assert c["counts"] == {"villages": 3, "roads": 0, "farmland": 0, "infrastructure": 0}, c["counts"]
    assert c["level"] == "partial"
    ok("missing, negative, text and None values are treated as 'no data' or read as numbers; nothing crashes")

    print("\n--- 5. The wording ---")
    for counts in ({}, {"villages": 1}, {"villages": 1, "roads": 1, "farmland": 1, "infrastructure": 1}):
        message = describe_coverage(counts)["message"]
        assert "confirmed" not in message.lower() and "safe" not in message.lower()
    ok("the messages never say 'confirmed' or 'safe'")

    print("\n" + SEP)
    print("  Reference coverage tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
