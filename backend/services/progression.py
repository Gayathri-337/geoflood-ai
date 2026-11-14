"""
GeoFlood AI backend - flood progression of an event (Phase 29a).

build_progression(analyses) compares the detected water of analyses that show THE SAME AREA on DIFFERENT
DATES. It is a plain function (no database, no web server), so backend/test_progression.py tests it on its own.

What counts as a comparable series (the rules are listed in CRITERIA and returned with every answer):
  * every analysis needs an observation date (the date the satellite took the image, entered at upload);
  * the footprints of its images must overlap by at least 80% of their combined extent;
  * at least two different dates are needed, otherwise there is nothing to compare;
  * two analyses of the same image and date (for example with and without a baseline) count once: the newest.
Anything that does not fit is listed with the reason. It is never charted against unrelated images.

What it measures is DETECTED SURFACE WATER, which includes rivers and lakes and does not depend on a baseline.
A change in detected water is not proof that the flood grew or shrank: rain, wet soil, wind on the water and
differences between images also change it. The answer says so.
"""

from datetime import datetime, timedelta, timezone

MIN_OVERLAP = 0.80                  # footprints must overlap by this share of their combined extent
GOOD_OVERLAP = 0.95                 # below this, the series carries a warning
SIMILAR_SHARE = 0.05                # a change under 5% of the earlier area ...
SIMILAR_KM2 = 0.05                  # ... or under 0.05 km2 is called "about the same"
VALID_AREA_WARN = 0.10              # the valid (non-empty) image area differs by more than 10%
EARLIEST_DATE = datetime(2000, 1, 1, tzinfo=timezone.utc)

CRITERIA = {
    "min_overlap": MIN_OVERLAP,
    "similar_change": f"under {SIMILAR_SHARE:.0%} of the earlier area or under {SIMILAR_KM2} km2",
    "rule": "Only analyses with an observation date that show the same area (footprints overlapping by at "
            "least 80%) on at least two different dates are compared.",
}
NOTE = ("This compares detected surface water (rivers and lakes included) between images of the same area. A "
        "change is not proof that the flood grew or shrank: rain, wet soil, wind on the water and differences "
        "between the images also change what the model detects.")

REASONS = {
    "no_date": "No observation date was entered for this image, so it cannot be placed in time.",
    "only_one_date": "The only dated image of this area, so there is nothing to compare it with.",
    "same_date_duplicate": "Another analysis of the same area and date is used instead.",
}


# ------------------------------------------------------------------ helpers
def validate_acquired_at(value):
    """
    The observation date typed at upload -> an aware UTC datetime, or None when nothing was entered.
    Raises ValueError (with a message for the user) when it is not a date, is before 2000 or is in the future.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("The observation date must look like 2026-10-27 or 2026-10-27T05:30:00Z.") from None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    if value < EARLIEST_DATE:
        raise ValueError("The observation date is before the year 2000.")
    if value > datetime.now(timezone.utc) + timedelta(days=1):
        raise ValueError("The observation date is in the future.")
    return value


def overlap(a, b):
    """Intersection over union of two [west, south, east, north] boxes: 1 = same area, 0 = no overlap."""
    w, s = max(a[0], b[0]), max(a[1], b[1])
    e, n = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, e - w) * max(0.0, n - s)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _direction(before, after):
    delta = after - before
    if abs(delta) <= max(SIMILAR_KM2, SIMILAR_SHARE * before):
        return "similar"
    return "more" if delta > 0 else "less"


def _unassigned(item, reason, **extra):
    return {"analysis_id": item["analysis_id"], "original_filename": item.get("original_filename"),
            "observed_at": item.get("acquired_at"), "reason": reason, "detail": REASONS[reason], **extra}


def _series_of(members, number):
    """members: analyses of one area on different dates (already de-duplicated), at least two."""
    members = sorted(members, key=lambda m: _aware(m["acquired_at"]))
    first = members[0]
    points = [{
        "analysis_id": m["analysis_id"], "original_filename": m.get("original_filename"),
        "observed_at": m["acquired_at"], "water_area_km2": _num(m.get("water_area_km2")),
        "water_pct_of_valid": _num(m.get("water_pct_of_valid")), "valid_area_km2": _num(m.get("valid_area_km2")),
        "baseline_method": m.get("baseline_method"),
        "overlap_with_first": round(overlap(first["bounds_wgs84"], m["bounds_wgs84"]), 4),
    } for m in members]

    changes = []
    for before, after in zip(points, points[1:]):
        a0, a1 = before["water_area_km2"], after["water_area_km2"]
        days = (_aware(after["observed_at"]) - _aware(before["observed_at"])).total_seconds() / 86400
        if a0 is None or a1 is None:
            changes.append({"from_analysis_id": before["analysis_id"], "to_analysis_id": after["analysis_id"],
                            "days": round(days, 2), "delta_km2": None, "pct_change": None, "direction": None})
            continue
        changes.append({
            "from_analysis_id": before["analysis_id"], "to_analysis_id": after["analysis_id"],
            "days": round(days, 2), "delta_km2": round(a1 - a0, 4),
            "pct_change": round((a1 - a0) / a0 * 100, 1) if a0 > 0 else None,    # no percentage from zero
            "direction": _direction(a0, a1),
        })

    areas = [p for p in points if p["water_area_km2"] is not None]
    summary = {"points": len(points), "first_analysis_id": points[0]["analysis_id"],
               "last_analysis_id": points[-1]["analysis_id"], "total_delta_km2": None, "total_pct_change": None,
               "peak_analysis_id": None}
    if len(areas) >= 2:
        a0, a1 = areas[0]["water_area_km2"], areas[-1]["water_area_km2"]
        summary["total_delta_km2"] = round(a1 - a0, 4)
        summary["total_pct_change"] = round((a1 - a0) / a0 * 100, 1) if a0 > 0 else None
    if areas:
        summary["peak_analysis_id"] = max(areas, key=lambda p: p["water_area_km2"])["analysis_id"]

    warnings = []
    lowest = min(p["overlap_with_first"] for p in points)
    if lowest < GOOD_OVERLAP:
        warnings.append(f"The images overlap by only {lowest:.0%} of their combined extent, not exactly the same "
                        f"area, so part of any change may come from the different coverage.")
    valid = [p["valid_area_km2"] for p in points if p["valid_area_km2"]]
    if len(valid) >= 2 and (max(valid) - min(valid)) / max(valid) > VALID_AREA_WARN:
        warnings.append(f"The valid (non-empty) area of the images differs by "
                        f"{(max(valid) - min(valid)) / max(valid):.0%}, so compare the water shares as well as the "
                        f"areas.")
    if any(p["water_area_km2"] is None for p in points):
        warnings.append("At least one analysis has no water area stored.")

    return {"series_id": number, "area_bounds_wgs84": first["bounds_wgs84"], "points": points, "changes": changes,
            "summary": summary, "warnings": warnings}


# ------------------------------------------------------------------ the main function
def build_progression(analyses, event_id=None):
    """
    analyses: dicts with analysis_id, original_filename, acquired_at (datetime or None), created_at,
              bounds_wgs84 [west, south, east, north], water_area_km2, water_pct_of_valid, valid_area_km2,
              baseline_method, status.   Analyses that are not 'completed' are left out.
    Returns {event_id, series: [...], unassigned: [...], criteria, note}.
    """
    done = [a for a in analyses if a.get("status", "completed") == "completed"]
    unassigned = [_unassigned(a, "no_date") for a in done if a.get("acquired_at") is None]
    dated = sorted((a for a in done if a.get("acquired_at") is not None),
                   key=lambda a: (_aware(a["acquired_at"]), a["analysis_id"]))

    groups = []                                       # each group: the images that show about the same area
    for item in dated:
        for group in groups:
            if overlap(group[0]["bounds_wgs84"], item["bounds_wgs84"]) >= MIN_OVERLAP:
                group.append(item)
                break
        else:
            groups.append([item])

    series = []
    for group in groups:
        by_date = {}
        for item in group:
            by_date.setdefault(_aware(item["acquired_at"]), []).append(item)
        kept = []
        for same_date in by_date.values():
            # the same image and date analysed more than once: use the newest analysis
            newest = max(same_date, key=lambda a: (_aware(a["created_at"]) if a.get("created_at") else _aware(a["acquired_at"]),
                                                   a["analysis_id"]))
            kept.append(newest)
            unassigned += [_unassigned(a, "same_date_duplicate", used_analysis_id=newest["analysis_id"])
                           for a in same_date if a is not newest]
        if len(kept) >= 2:
            series.append(_series_of(kept, len(series) + 1))
        else:
            unassigned.append(_unassigned(kept[0], "only_one_date"))

    unassigned.sort(key=lambda u: u["analysis_id"])
    return {"event_id": event_id, "series": series, "unassigned": unassigned, "criteria": CRITERIA, "note": NOTE}
