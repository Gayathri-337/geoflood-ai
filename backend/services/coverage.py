"""
GeoFlood AI backend - how much reference data (OpenStreetMap) exists inside an analysed image (Phase 30).

Impact figures only count what is stored in reference_features. If nothing is stored for an area, an impact of 0
means "no data", not "no impact". This module turns the counts into one honest sentence that the web page and
the PDF report both show. It does no database work, so it can be tested on its own.
"""

LAYERS = ("villages", "roads", "farmland", "infrastructure")

# (one, many) as shown to people
NAMES = {
    "villages": ("village", "villages"),
    "roads": ("road segment", "road segments"),
    "farmland": ("farmland area", "farmland areas"),
    "infrastructure": ("facility", "facilities"),
}
# the shorter plural used when a layer is empty
SHORT = {"villages": "villages", "roads": "roads", "farmland": "farmland", "infrastructure": "facilities"}

CAUTION = "OpenStreetMap is incomplete, so impact figures are lower bounds."


def _count(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


def _join(items):
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def describe_coverage(counts):
    """
    counts: {"villages": n, "roads": n, "farmland": n, "infrastructure": n} - reference features inside the image.
    Returns {"counts", "empty_layers", "level", "message"}; level is 'none' (nothing at all), 'partial' (some layers
    are empty) or 'ok'.
    """
    clean = {layer: _count((counts or {}).get(layer)) for layer in LAYERS}
    empty = [layer for layer in LAYERS if clean[layer] == 0]

    if len(empty) == len(LAYERS):
        level = "none"
        message = ("No villages, roads, farmland or facilities from the reference data (OpenStreetMap) lie inside "
                   "this image. An impact of 0 here means there is no data for this area, not that nothing was "
                   "affected.")
    elif empty:
        level = "partial"
        names = _join([SHORT[layer] for layer in empty])
        message = (f"The reference data has no {names} inside this image, so a 0 for those means no data, not "
                   f"that nothing was affected. {CAUTION}")
    else:
        level = "ok"
        parts = [f"{clean[layer]} {NAMES[layer][0 if clean[layer] == 1 else 1]}" for layer in LAYERS]
        message = f"Reference data inside this image: {_join(parts)}. {CAUTION}"

    return {"counts": clean, "empty_layers": empty, "level": level, "message": message}
