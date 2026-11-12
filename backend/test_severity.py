"""
GeoFlood AI - Phase 25 test: the severity rules (no database needed).

Usage (project root):  python -m backend.test_severity
"""

import math

from backend.services import severity as sev

SEP = "=" * 70


def ok(message):
    print(f"  [OK] {message}")


def just_below(limit):
    return limit - 1 if isinstance(limit, int) else limit - 0.001


def analysis(baseline="jrc", new_pct=0.0, water_pct=0.0):
    return {"baseline_method": baseline, "new_flood_pct_of_valid": new_pct, "water_pct_of_valid": water_pct}


def summary(road_km=0.0, villages=0, farmland_km2=0.0, facilities=None, computed=True):
    """facilities: a number (that many schools) or a dict of facilities INSIDE per category, e.g. {"hospital": 1}."""
    categories = facilities if isinstance(facilities, dict) else ({"school": facilities} if facilities else {})
    total = sum(categories.values())
    return {
        "last_computed_at": "2026-11-08T16:00:00Z" if computed else None,
        "villages": {"count": villages, "inside": villages, "near": 0},
        "roads": {"count": 1, "flooded_length_km": road_km, "bridges": {"count": 0, "length_km": 0}},
        "farmland": {"count": 0, "flooded_area_km2": farmland_km2},
        "infrastructure": {"count": total, "inside": total, "near": 0,
                           "by_category": {c: {"inside": n, "near": 0} for c, n in categories.items()}},
    }


def levels(result):
    return {i["key"]: i["level"] for i in result["indicators"]}


def test_rules_are_sane():
    assert sev.LEVELS == ("low", "moderate", "high", "severe")
    assert set(sev.THRESHOLDS) == set(sev.ORDER) == set(sev.UNITS)
    for key, limits in sev.THRESHOLDS.items():
        real = [x for x in limits if x is not None]
        assert len(limits) == 3 and real == sorted(real) and len(set(real)) == len(real), key
    ok("every indicator has 3 steps, strictly increasing (a step may be skipped), and a unit")
    assert set(sev.CRITICAL_FACILITIES) == {"hospital", "clinic", "police", "fire_station"}
    assert "shelter" not in sev.CRITICAL_FACILITIES and sev.LEVELS[sev.CRITICAL_MIN_INDEX] == "high"
    ok("critical facilities: hospital, clinic, police, fire_station (a shelter is not critical); one is at least 'high'")


def test_boundaries():
    for key, limits in sev.THRESHOLDS.items():
        for step, limit in enumerate(limits, start=1):
            if limit is None:
                continue
            below = just_below(limit)
            expected_below = max([s for s, x in enumerate(limits, start=1) if x is not None and x <= below] + [0])
            assert sev.level_index(limit, limits) == step, (key, limit)
            assert sev.level_index(below, limits) == expected_below, (key, below)
        assert sev.level_index(0, limits) == 0
        assert sev.level_index(10 ** 9, limits) == 3
    ok("at each limit the level starts; just below it the level is the one before; 0 is low and a huge value is severe")
    facilities = sev.THRESHOLDS["facilities"]
    assert [sev.level_index(n, facilities) for n in (0, 1, 2, 3, 10)] == [0, 1, 2, 3, 3]
    ok("facilities inside: none is low, one is moderate, two are high, three or more are severe")
    assert [sev.level_index(n, (None, 1, 3)) for n in (0, 1, 2, 3)] == [0, 2, 2, 3]
    ok("a rule with a skipped step still works (None = no 'moderate' step: the first limit starts at 'high')")


def test_overall_level():
    r = sev.classify(analysis(new_pct=5.0), summary(computed=False))
    assert r["level"] == "moderate" and r["impact_included"] is False and r["driven_by"] == ["area_pct"]
    assert all(i["value"] is None and i["level"] is None for i in r["indicators"] if i["key"] != "area_pct")
    ok("impact not computed: only the water area counts; impact indicators have no value and no level")

    r = sev.classify(analysis(new_pct=0.5), summary(facilities=1))
    assert r["level"] == "moderate" and r["driven_by"] == ["facilities"] and levels(r)["area_pct"] == "low"
    r = sev.classify(analysis(new_pct=0.5), summary(facilities=2))
    assert r["level"] == "high" and r["driven_by"] == ["facilities"] and levels(r)["area_pct"] == "low"
    ok("the worst indicator wins: a tiny water area but 1 facility inside -> moderate, 2 facilities -> high")

    r = sev.classify(analysis(new_pct=12.0), summary(road_km=2.5))
    assert r["level"] == "high" and r["driven_by"] == ["area_pct", "road_km"]
    ok("two indicators at the top level are both listed as the reason")

    r = sev.classify(analysis(new_pct=0.1), summary())
    assert r["level"] == "low" and r["driven_by"] == [] and r["impact_included"] is True
    ok("everything small -> low, and nothing is blamed")

    r = sev.classify(analysis(new_pct=30.0), summary(villages=7, farmland_km2=6, road_km=9, facilities=4))
    assert r["level"] == "severe" and set(r["driven_by"]) == set(sev.ORDER)
    ok("everything at the top -> severe, decided by all five")


def test_facility_rule():
    def facility(**inside):
        r = sev.classify(analysis(new_pct=0.1), summary(facilities=inside))
        item = next(i for i in r["indicators"] if i["key"] == "facilities")
        return r, item

    expectations = [
        ({"school": 1}, "moderate"), ({"college": 1}, "moderate"), ({"shelter": 1}, "moderate"),
        ({"unknown": 1}, "moderate"),
        ({"hospital": 1}, "high"), ({"clinic": 1}, "high"), ({"police": 1}, "high"), ({"fire_station": 1}, "high"),
        ({"school": 2}, "high"), ({"school": 1, "college": 1}, "high"),
        ({"hospital": 1, "clinic": 1}, "high"),
        ({"school": 3}, "severe"), ({"hospital": 2, "school": 1}, "severe"), ({"shelter": 3}, "severe"),
    ]
    for inside, level in expectations:
        r, item = facility(**inside)
        assert item["level"] == level and r["level"] == level, (inside, item["level"], r["level"])
    ok("1 ordinary facility is moderate; 1 critical one, or 2 of any kind, is high; 3 or more is severe")

    r, item = facility(hospital=1, school=2)
    assert item["detail"] == "1 critical" and "hospital" in item["note"] and "schools" in item["note"]
    ok("the facilities indicator says how many of them are critical and explains the rule")

    r = sev.classify(analysis(new_pct=0.1), summary(computed=False, facilities={"hospital": 1}))
    item = next(i for i in r["indicators"] if i["key"] == "facilities")
    assert item["value"] is None and item["level"] is None and item["detail"] is None and r["level"] == "low"
    r = sev.classify(analysis(new_pct=0.1), summary())
    assert next(i for i in r["indicators"] if i["key"] == "facilities")["detail"] == "0 critical"
    assert sev.indicator_index("facilities", 1, critical_inside=1) == 2
    assert sev.indicator_index("facilities", 1, critical_inside=0) == 1
    assert sev.indicator_index("road_km", 1.0, critical_inside=5) == 1       # only facilities use the critical rule
    ok("without computed impact the facilities have no level; the critical rule affects only the facilities indicator")


def test_baseline_choice():
    r = sev.classify(analysis("none", new_pct=None, water_pct=12.0), None)
    assert r["level"] == "high" and "detected water" in r["indicators"][0]["label"]
    r = sev.classify(analysis("jrc", new_pct=1.0, water_pct=40.0), None)
    assert r["level"] == "low" and "new water" in r["indicators"][0]["label"]
    ok("without a baseline the detected water counts; with one, only the NEW water counts (not the permanent water)")


def test_robustness():
    for bad in (None, "abc", float("nan")):
        r = sev.classify(analysis(new_pct=bad), summary(road_km=bad))
        assert r["level"] == "low" and levels(r)["area_pct"] == "low", bad
    r = sev.classify({"baseline_method": "jrc"}, {"last_computed_at": "x"})
    assert r["level"] == "low"
    assert sev.classify(analysis(), None)["impact_included"] is False
    assert sev.classify(analysis(), {"last_computed_at": None})["impact_included"] is False
    for item in sev.classify(analysis(), summary())["indicators"]:
        assert item["value"] is None or not math.isnan(item["value"])
    ok("missing, text and NaN values are treated as zero instead of crashing")


def test_worked_examples():
    # Numbers from this project's own demo analyses. These checks fix the CURRENT thresholds:
    # if you change THRESHOLDS on purpose, update the expected levels here (and see what changes).
    cases = [
        ("India_828067 (thin river channel)", analysis(new_pct=2.098), summary(), "moderate", ["area_pct"]),
        ("India_1018327 (56 m of road)", analysis(new_pct=8.60), summary(road_km=0.056), "moderate", ["area_pct"]),
        ("India_591317", analysis(new_pct=16.573), summary(), "high", ["area_pct"]),
        ("India_747992 (largest flood)", analysis("none", water_pct=27.2), summary(road_km=2.32), "severe", ["area_pct"]),
    ]
    for name, a, s, level, driven in cases:
        r = sev.classify(a, s)
        assert (r["level"], r["driven_by"]) == (level, driven), (name, r["level"], r["driven_by"])
        print(f"       {name:<36} -> {r['level']:<9} decided by {', '.join(r['driven_by'])}")
    ok("the four demo chips")


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 25 Severity Rules Test")
    print(SEP)
    print()
    for test in (test_rules_are_sane, test_boundaries, test_overall_level, test_facility_rule,
                 test_baseline_choice, test_robustness, test_worked_examples):
        test()
    print("\n" + SEP)
    print("  Severity rules tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()