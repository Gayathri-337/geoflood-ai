"""
GeoFlood AI backend - flood severity classification (Phase 25).

PROVISIONAL RULES. The thresholds below were chosen by the project author to be simple and explainable.
They are NOT an official standard and are NOT calibrated against damage or ground-truth severity data
(the dataset has none). Change them in THRESHOLDS; the overall level follows automatically.

How it works
  * Five indicators are each turned into a level: low, moderate, high or severe.
  * The overall level is the HIGHEST level reached by any indicator ("the worst indicator wins").
  * The impact indicators need the impact to have been computed; before that only the water area counts.
  * OpenStreetMap is incomplete, so the impact indicators (and therefore the level) are lower bounds.
"""

# Same words as the CHECK constraint on flood_analysis.severity in database/schema.sql
LEVELS = ("low", "moderate", "high", "severe")

# Lower limit of each level: (moderate_from, high_from, severe_from). None = that step does not exist.
THRESHOLDS = {
    "area_pct": (2.0, 10.0, 25.0),    # % of the valid image covered by new water (detected water without a baseline)
    "road_km": (0.5, 2.0, 5.0),       # km of flooded road, bridges excluded
    "villages": (1, 3, 6),            # villages INSIDE the flooded area
    "farmland_km2": (0.1, 1.0, 5.0),  # km2 of flooded farmland
    "facilities": (1, 2, 3),          # facilities INSIDE the flooded area, by number (a critical one is 'high' alone)
}

UNITS = {"area_pct": "%", "road_km": "km", "villages": "", "farmland_km2": "km²", "facilities": ""}
ORDER = ("area_pct", "road_km", "villages", "farmland_km2", "facilities")

NOTE = (
    "Provisional rules chosen for this project: not an official standard and not calibrated against damage data. "
    "The highest level reached by any indicator decides the overall level. OpenStreetMap is incomplete, so the "
    "impact indicators, and therefore the level, are lower bounds."
)


# OpenStreetMap `amenity` values that count as CRITICAL facilities: ONE of them inside the flooded area is
# already 'high'. School, college and shelter are collected too, but they only count by number
# (amenity=shelter in OpenStreetMap is usually a simple weather shelter, not an evacuation centre).
CRITICAL_FACILITIES = ("hospital", "clinic", "police", "fire_station")
CRITICAL_MIN_INDEX = 2   # 2 = 'high'

FACILITY_NOTE = (
    "A hospital, clinic, police station or fire station inside counts as high on its own. "
    "Other facilities (schools, colleges, shelters) count by number."
)


def indicator_index(key, value, critical_inside=0):
    """0 = low ... 3 = severe for one indicator. critical_inside only matters for the facilities indicator."""
    index = level_index(value, THRESHOLDS[key])
    if key == "facilities" and critical_inside >= 1:
        index = max(index, CRITICAL_MIN_INDEX)
    return index


def level_index(value, limits):
    """0 = low ... 3 = severe. limits = (moderate_from, high_from, severe_from); a None step is skipped."""
    index = 0
    for step, limit in enumerate(limits, start=1):
        if limit is not None and value >= limit:
            index = step
    return index


def _number(value):
    """A float, or None for missing / non-numeric / NaN values."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _dig(data, *path):
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _critical_inside(summary):
    """How many critical facilities are inside the flooded area, from the impact summary's categories."""
    by_category = _dig(summary, "infrastructure", "by_category")
    if not isinstance(by_category, dict):
        return 0
    return sum(int(_number(_dig(by_category, category, "inside")) or 0) for category in CRITICAL_FACILITIES)


def _label(key, has_baseline):
    if key == "area_pct":
        return "Share of the image covered by " + ("new water (vs baseline)" if has_baseline else "detected water")
    return {
        "road_km": "Flooded road length (bridges excluded)",
        "villages": "Villages inside the flooded area",
        "farmland_km2": "Flooded farmland area",
        "facilities": "Facilities inside the flooded area",
    }[key]


def classify(analysis, summary):
    """
    analysis : the analysis as returned by the API (needs baseline_method, water_pct_of_valid, new_flood_pct_of_valid)
    summary  : the impact summary as returned by the API, or None
    Returns {level, driven_by, impact_included, indicators, note}.
    """
    has_baseline = (analysis.get("baseline_method") or "none") != "none"
    area = _number(analysis.get("new_flood_pct_of_valid" if has_baseline else "water_pct_of_valid"))
    impact_included = bool(summary and summary.get("last_computed_at"))

    values = {"area_pct": 0.0 if area is None else area}
    if impact_included:
        values["road_km"] = _number(_dig(summary, "roads", "flooded_length_km")) or 0.0
        values["villages"] = _number(_dig(summary, "villages", "inside")) or 0.0
        values["farmland_km2"] = _number(_dig(summary, "farmland", "flooded_area_km2")) or 0.0
        values["facilities"] = _number(_dig(summary, "infrastructure", "inside")) or 0.0

    critical = _critical_inside(summary) if impact_included else 0
    indicators, indexes = [], {}
    for key in ORDER:
        limits = THRESHOLDS[key]
        value = values.get(key)
        index = None if value is None else indicator_index(key, value, critical)
        if index is not None:
            indexes[key] = index
        indicators.append({
            "key": key,
            "label": _label(key, has_baseline),
            "unit": UNITS[key],
            "value": value,
            "level": None if index is None else LEVELS[index],
            "thresholds": {"moderate": limits[0], "high": limits[1], "severe": limits[2]},
            "detail": f"{critical} critical" if key == "facilities" and value is not None else None,
            "note": FACILITY_NOTE if key == "facilities" else None,
        })

    overall = max(indexes.values())      # the area indicator is always present
    return {
        "level": LEVELS[overall],
        "driven_by": [key for key in ORDER if indexes.get(key) == overall] if overall > 0 else [],
        "impact_included": impact_included,
        "indicators": indicators,
        "note": NOTE,
    }