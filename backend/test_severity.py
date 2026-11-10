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


def summary(road_km=0.0, villages=0, farmland_km2=0.0, facilities=0, computed=True):
    return {
        "last_computed_at": "2026-11-08T16:00:00Z" if computed else None,
        "villages": {"count": villages, "inside": villages, "near": 0},
        "roads": {"count": 1, "flooded_length_km": road_km, "bridges": {"count": 0, "length_km": 0}},
        "farmland": {"count": 0, "flooded_area_km2": farmland_km2},
        "infrastructure": {"count": facilities, "inside": facilities, "near": 0, "by_category": {}},
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
    assert sev.level_index(0, sev.THRESHOLDS["facilities"]) == 0
    assert sev.level_index(1, sev.THRESHOLDS["facilities"]) == 2
    assert sev.level_index(3, sev.THRESHOLDS["facilities"]) == 3
    ok("facilities: none is low, a single facility inside is already high, three or more is severe")


def test_overall_level():
    r = sev.classify(analysis(new_pct=5.0), summary(computed=False))
    assert r["level"] == "moderate" and r["impact_included"] is False and r["driven_by"] == ["area_pct"]
    assert all(i["value"] is None and i["level"] is None for i in r["indicators"] if i["key"] != "area_pct")
    ok("impact not computed: only the water area counts; impact indicators have no value and no level")

    r = sev.classify(analysis(new_pct=0.5), summary(facilities=1))
    assert r["level"] == "high" and r["driven_by"] == ["facilities"] and levels(r)["area_pct"] == "low"
    ok("the worst indicator wins: tiny water area but one facility inside -> high, decided by the facilities")

    r = sev.classify(analysis(new_pct=12.0), summary(road_km=2.5))
    assert r["level"] == "high" and r["driven_by"] == ["area_pct", "road_km"]
    ok("two indicators at the top level are both listed as the reason")

    r = sev.classify(analysis(new_pct=0.1), summary())
    assert r["level"] == "low" and r["driven_by"] == [] and r["impact_included"] is True
    ok("everything small -> low, and nothing is blamed")

    r = sev.classify(analysis(new_pct=30.0), summary(villages=7, farmland_km2=6, road_km=9, facilities=4))
    assert r["level"] == "severe" and set(r["driven_by"]) == set(sev.ORDER)
    ok("everything at the top -> severe, decided by all five")


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
    for test in (test_rules_are_sane, test_boundaries, test_overall_level, test_baseline_choice,
                 test_robustness, test_worked_examples):
        test()
    print("\n" + SEP)
    print("  Severity rules tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
