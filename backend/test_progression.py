"""
GeoFlood AI - Phase 29a test: the flood progression rules, on SYNTHETIC data (no database, no server needed).

Every number below is invented for the test. None of it is a real analysis result.
Usage (project root):  python -m backend.test_progression
"""

import copy
from datetime import datetime, timedelta, timezone

from backend.services.progression import build_progression, overlap, validate_acquired_at

SEP = "=" * 70
UTC = timezone.utc
AREA = [93.40, 26.30, 93.46, 26.35]
OTHER_AREA = [94.40, 27.30, 94.46, 27.35]


def ok(message):
    print(f"  [OK] {message}")


def day(n):
    return datetime(2026, 10, 1, 6, 0, tzinfo=UTC) + timedelta(days=n)


def item(analysis_id, acquired, water, bounds=AREA, valid=25.0, created=None, **extra):
    base = {"analysis_id": analysis_id, "original_filename": f"synthetic_{analysis_id}.tif", "acquired_at": acquired,
            "created_at": created or day(30 + analysis_id), "status": "completed", "bounds_wgs84": bounds,
            "water_area_km2": water, "water_pct_of_valid": None if water is None else water / valid * 100,
            "valid_area_km2": valid, "baseline_method": "none"}
    base.update(extra)
    return base


def raises(text, value):
    try:
        validate_acquired_at(value)
    except ValueError as err:
        assert text in str(err), str(err)
        return
    raise AssertionError(f"{value!r} should have been refused")


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 29a Flood Progression Test (synthetic data)")
    print(SEP)

    # ------------------------------------------------------------ 1
    print("\n--- 1. Three dates of one area ---")
    result = build_progression([item(3, day(12), 6.8), item(1, day(0), 2.5), item(2, day(6), 4.2)], event_id=9)
    assert result["event_id"] == 9 and len(result["series"]) == 1 and result["unassigned"] == []
    s = result["series"][0]
    assert [p["analysis_id"] for p in s["points"]] == [1, 2, 3], "points must be in the order of the dates"
    assert [(c["from_analysis_id"], c["to_analysis_id"], c["days"]) for c in s["changes"]] == [(1, 2, 6.0), (2, 3, 6.0)]
    assert [c["delta_km2"] for c in s["changes"]] == [1.7, 2.6]
    assert [c["pct_change"] for c in s["changes"]] == [68.0, 61.9]
    assert [c["direction"] for c in s["changes"]] == ["more", "more"]
    assert s["summary"]["total_delta_km2"] == 4.3 and s["summary"]["total_pct_change"] == 172.0
    assert s["summary"]["peak_analysis_id"] == 3 and s["warnings"] == []
    assert "not proof" in result["note"] and result["criteria"]["min_overlap"] == 0.8
    ok("sorted by date, +1.7 and +2.6 km2 between the dates, +4.3 km2 (+172%) overall, no warnings")

    # ------------------------------------------------------------ 2
    print("\n--- 2. Decrease, and 'about the same' ---")
    s = build_progression([item(1, day(0), 8.0), item(2, day(6), 4.0), item(3, day(12), 4.1)])["series"][0]
    assert [c["direction"] for c in s["changes"]] == ["less", "similar"]
    assert s["changes"][0]["pct_change"] == -50.0 and s["summary"]["peak_analysis_id"] == 1
    s = build_progression([item(1, day(0), 0.0), item(2, day(6), 1.0)])["series"][0]
    assert s["changes"][0]["pct_change"] is None and s["changes"][0]["direction"] == "more"
    ok("less / similar are told apart; no percentage is made up when the first area is 0")

    # ------------------------------------------------------------ 3
    print("\n--- 3. What is not compared ---")
    result = build_progression([
        item(1, None, 5.0),                                   # no date
        item(2, day(0), 3.0), item(3, day(6), 4.0),           # a real pair
        item(4, day(3), 9.0, bounds=OTHER_AREA),              # another place
        item(5, day(2), 1.0, status="failed"),                # not completed
    ])
    assert len(result["series"]) == 1
    assert [p["analysis_id"] for p in result["series"][0]["points"]] == [2, 3]
    reasons = {u["analysis_id"]: u["reason"] for u in result["unassigned"]}
    assert reasons == {1: "no_date", 4: "only_one_date"}, reasons
    assert all(u["detail"] for u in result["unassigned"])
    ok("no date, another area and a failed run are left out of the series, each with a reason; the pair is kept")

    # ------------------------------------------------------------ 4
    print("\n--- 4. Same image analysed twice ---")
    result = build_progression([item(1, day(0), 3.0), item(2, day(0), 3.0, created=day(40)),
                                item(3, day(6), 4.0)])
    s = result["series"][0]
    assert [p["analysis_id"] for p in s["points"]] == [2, 3], "the newer analysis of the same date is used"
    assert result["unassigned"] == [{"analysis_id": 1, "original_filename": "synthetic_1.tif",
                                     "observed_at": day(0), "reason": "same_date_duplicate",
                                     "detail": result["unassigned"][0]["detail"], "used_analysis_id": 2}]
    only = build_progression([item(1, day(0), 3.0), item(2, day(0), 3.0)])
    assert only["series"] == [] and {u["reason"] for u in only["unassigned"]} == {"same_date_duplicate", "only_one_date"}
    ok("two analyses of one date count once (the newest); a single date alone is not a series")

    # ------------------------------------------------------------ 5
    print("\n--- 5. Areas that only partly overlap ---")
    shifted = [93.401, 26.30, 93.461, 26.35]                     # almost the same box
    half = [93.43, 26.30, 93.49, 26.35]                          # half of it is different
    assert abs(overlap(AREA, AREA) - 1.0) < 1e-9 and overlap(AREA, OTHER_AREA) == 0.0
    assert overlap(AREA, half) < 0.8 and overlap(AREA, shifted) > 0.95
    s = build_progression([item(1, day(0), 3.0), item(2, day(6), 4.0, bounds=shifted)])["series"][0]
    assert s["warnings"] == []
    near = [93.404, 26.30, 93.464, 26.35]                       # about 87% overlap: same series, with a warning
    assert 0.8 <= overlap(AREA, near) < 0.95
    s = build_progression([item(1, day(0), 3.0), item(2, day(6), 4.0, bounds=near)])["series"][0]
    assert len(s["warnings"]) == 1 and "overlap" in s["warnings"][0]
    assert build_progression([item(1, day(0), 3.0), item(2, day(6), 4.0, bounds=half)])["series"] == []
    ok("95%+ overlap is silent; 80-95% is one series with a warning; under 80% is a different area")

    # ------------------------------------------------------------ 6
    print("\n--- 6. Valid area and missing numbers ---")
    s = build_progression([item(1, day(0), 3.0, valid=25.0), item(2, day(6), 4.0, valid=20.0)])["series"][0]
    assert len(s["warnings"]) == 1 and "valid" in s["warnings"][0]
    s = build_progression([item(1, day(0), None), item(2, day(6), 4.0)])["series"][0]
    assert s["changes"][0]["delta_km2"] is None and s["changes"][0]["direction"] is None
    assert any("no water area" in w for w in s["warnings"]) and s["summary"]["total_delta_km2"] is None
    assert build_progression([])["series"] == [] and build_progression([])["unassigned"] == []
    ok("a 20% difference in valid area is warned about; a missing area gives no change figure instead of 0")

    # ------------------------------------------------------------ 7
    print("\n--- 7. The observation date typed at upload ---")
    assert validate_acquired_at(None) is None and validate_acquired_at("  ") is None
    assert validate_acquired_at("2026-10-27") == datetime(2026, 10, 27, tzinfo=UTC)
    assert validate_acquired_at("2026-10-27T05:30:00Z") == datetime(2026, 10, 27, 5, 30, tzinfo=UTC)
    assert validate_acquired_at("2026-10-27T11:00:00+05:30") == datetime(2026, 10, 27, 5, 30, tzinfo=UTC)
    assert validate_acquired_at(datetime(2026, 10, 27)).tzinfo is not None
    raises("must look like", "yesterday")
    raises("must look like", "27/10/2026")
    raises("before the year 2000", "1999-12-31")
    raises("in the future", (datetime.now(UTC) + timedelta(days=30)).isoformat())
    ok("a date or a date-time is accepted (time zones converted to UTC); text, old and future dates are refused")

    # ------------------------------------------------------------ 8
    print("\n--- 8. The input is not changed ---")
    data = [item(1, day(0), 3.0), item(2, day(6), 4.0), item(3, None, 1.0)]
    before = copy.deepcopy(data)
    build_progression(data)
    assert data == before
    ok("the analyses passed in are left as they were")

    print("\n" + SEP)
    print("  Flood progression tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
