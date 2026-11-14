"""
GeoFlood AI backend - PDF report of one analysis (Phase 28).

build_report(data) turns plain Python data into the bytes of a PDF. It does not touch the database or the
web server, so it can be tested on its own (see backend/test_report.py). The router
(backend/routers/report.py) gathers the data and calls it.

Rules this report follows (they are part of the project's accuracy requirements):
  * Detected water is not confirmed flooding. "New water" is only "not on the baseline layer".
  * A bridge over the water is shown separately and is never counted as a flooded road.
  * "Inside the flooded area" and "near the flooded area" are always kept apart.
  * Impact figures are estimates from OpenStreetMap, which is incomplete: lower bounds, not confirmed damage.
  * Something that was not computed or not recorded is written as such. It is never shown as zero.
  * The severity rules are provisional, and the report says so.
"""

import io
import re
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import PathPatch, Patch
from matplotlib.path import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

TITLE = "GeoFlood AI: Flood Analysis Report"
NOT_RECORDED = "not recorded"
MAX_LIST = 15          # how many villages, roads, facilities or actions are listed by name

# Same colours as the web map (frontend/src/map/layers.js and actions.js)
MAP_COLORS = {
    "permanent_water": "#1f78b4", "new_flood": "#e6550d", "water": "#2b8cbe", "farmland": "#33a02c",
    "roads": "#d7191c", "villages": "#6a3d9a", "infrastructure": "#111111", "bridges": "#6b7280",
}
PIN_COLORS = {"low": "#6c757d", "medium": "#0d6efd", "high": "#fd7e14", "critical": "#dc3545"}
LEVEL_COLORS = {"low": "#198754", "moderate": "#ffc107", "high": "#dc3545", "severe": "#212529"}
LEVEL_TEXT = {"low": "#ffffff", "moderate": "#000000", "high": "#ffffff", "severe": "#ffffff"}
TYPE_LABEL = {"evacuation": "Evacuation", "rescue": "Rescue", "shelter": "Shelter",
              "relief_distribution": "Relief distribution", "road_closure": "Road closure",
              "medical": "Medical", "other": "Other"}
STATUS_LABEL = {"planned": "Planned", "in_progress": "In progress", "completed": "Completed",
                "cancelled": "Cancelled"}

LIMITATIONS = [
    "The model detects surface-water-like areas in Sentinel-1 radar images. Detected water is not "
    "confirmed flooding. Rivers and lakes are included unless a baseline layer was used.",
    "\"New water\" means water that is not on the baseline layer. It is an approximation: it also contains "
    "seasonal water and anything the baseline layer missed.",
    "Model quality differs from image to image. In the project's own check on 14 India test chips, the "
    "flooded area of single chips with at least 1 km2 of labelled water was off by about 21% on average "
    "(from -39% to +15%). The confidence shown is the model's average certainty, not an accuracy.",
    "Villages, roads, farmland and facilities come from OpenStreetMap, which is incomplete or out of date in "
    "places. The impact figures are estimates and lower bounds, not confirmed damage. A feature that is "
    "missing from OpenStreetMap is not counted, so a low figure does not mean that nothing was affected.",
    "A road on a bridge over the detected water is listed as a bridge and is not counted as a flooded road. "
    "A facility counts as inside the flooded area only when it lies within the detected water; "
    "facilities that are only near the water are listed separately.",
    "The severity level follows provisional rules chosen for this project. They are not an official standard "
    "and are not calibrated against damage data.",
    "Emergency actions are a coordination aid for this project and not an official emergency system.",
    "This report is a model estimate for a college project. It is not an official flood map and must not be "
    "the only basis for an emergency decision.",
]


# ------------------------------------------------------------------ small helpers
def safe(value, default=NOT_RECORDED) -> str:
    """Plain text that the standard PDF fonts can print (anything else becomes '?')."""
    if value is None or str(value).strip() == "":
        return default
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", str(value))
    return text.encode("cp1252", "replace").decode("cp1252")


def para_text(value, default=NOT_RECORDED) -> str:
    """safe() plus the escaping that a reportlab Paragraph needs (it reads <, > and & as markup)."""
    return escape(safe(value, default))


def number(value, digits=2, default="not available") -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return default if n != n else f"{n:,.{digits}f}"


def moment(value, default=NOT_RECORDED) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return safe(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    return safe(value)                                   # a plain date


# ------------------------------------------------------------------ the flood extent map
def _parts(geometry):
    """Yield ('poly' | 'line' | 'point', coordinates) for every simple part of a GeoJSON geometry."""
    if not isinstance(geometry, dict):
        return
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Polygon" and coords:
        yield "poly", coords
    elif kind == "MultiPolygon":
        for polygon in coords or []:
            yield "poly", polygon
    elif kind == "LineString" and coords:
        yield "line", coords
    elif kind == "MultiLineString":
        for line in coords or []:
            yield "line", line
    elif kind == "Point" and coords:
        yield "point", coords
    elif kind == "MultiPoint":
        for point in coords or []:
            yield "point", point
    elif kind == "GeometryCollection":
        for inner in geometry.get("geometries") or []:
            yield from _parts(inner)


def _polygon_patch(rings, **style):
    vertices, codes = [], []
    for ring in rings:
        if len(ring) < 3:
            continue
        points = np.asarray([(p[0], p[1]) for p in ring], dtype=float)
        vertices.append(points)
        codes.extend([Path.MOVETO] + [Path.LINETO] * (len(points) - 2) + [Path.CLOSEPOLY])
    if not vertices:
        return None
    return PathPatch(Path(np.concatenate(vertices), codes), **style)


def _draw(ax, collection, draw_poly, draw_line, draw_point):
    for feature in (collection or {}).get("features", []):
        for kind, coords in _parts(feature.get("geometry")):
            try:
                if kind == "poly":
                    patch = draw_poly(coords)
                    if patch is not None:
                        ax.add_patch(patch)
                elif kind == "line":
                    xs, ys = zip(*[(p[0], p[1]) for p in coords])
                    draw_line(xs, ys)
                else:
                    draw_point(coords[0], coords[1])
            except (TypeError, ValueError, IndexError):
                continue                                  # one broken geometry must not stop the report


def render_map(data) -> tuple[bytes, int]:
    """
    The flood extent map as PNG bytes, and how many action pins fall outside it.
    It is drawn from the stored geometry only (no base map is downloaded), so it works offline.
    """
    analysis = data["analysis"]
    west, south, east, north = analysis["bounds_wgs84"]
    has_baseline = (analysis.get("baseline_method") or "none") != "none"
    layers = (data.get("impact") or {}).get("layers") or {}

    pad_x, pad_y = max((east - west) * 0.12, 1e-4), max((north - south) * 0.12, 1e-4)
    view = (west - pad_x, east + pad_x, south - pad_y, north + pad_y)

    figure = Figure(figsize=(6.6, 4.9), dpi=200)
    FigureCanvasAgg(figure)
    ax = figure.add_axes([0.09, 0.2, 0.88, 0.76])
    ax.set_facecolor("#f4f1ea")

    # the analysed image
    ax.add_patch(PathPatch(Path([(west, south), (east, south), (east, north), (west, north), (west, south)]),
                           facecolor="white", edgecolor="#444444", linestyle="--", linewidth=0.9, zorder=1))

    def polys(colour, alpha, z):
        return lambda rings: _polygon_patch(rings, facecolor=colour, edgecolor=colour, linewidth=0.3,
                                            alpha=alpha, zorder=z)

    def lines(colour, width, z):
        return lambda xs, ys: ax.plot(xs, ys, color=colour, linewidth=width, zorder=z, solid_capstyle="round")

    def points(colour, marker, size, z):
        return lambda x, y: ax.scatter([x], [y], c=colour, marker=marker, s=size, zorder=z, edgecolors="white",
                                       linewidths=0.4)

    nothing = lambda *args: None                                                   # noqa: E731

    # detected water, farmland (flooded part), villages, roads, bridges, facilities
    for feature in (data.get("zones") or {}).get("features", []):
        zone = (feature.get("properties") or {}).get("zone_type")
        colour = MAP_COLORS["new_flood"] if zone == "new_flood" else (
            MAP_COLORS["permanent_water"] if zone == "permanent_water" else MAP_COLORS["water"])
        _draw(ax, {"features": [feature]}, polys(colour, 0.8, 3), nothing, nothing)
    _draw(ax, layers.get("farmland"), polys(MAP_COLORS["farmland"], 0.45, 2), nothing, nothing)
    _draw(ax, layers.get("villages"), polys(MAP_COLORS["villages"], 0.25, 4), nothing,
          points(MAP_COLORS["villages"], "o", 22, 5))
    roads = {"type": "FeatureCollection", "features": [
        f for f in (layers.get("roads") or {}).get("features", []) if not (f.get("properties") or {}).get("on_bridge")]}
    bridges = {"type": "FeatureCollection", "features": [
        f for f in (layers.get("roads") or {}).get("features", []) if (f.get("properties") or {}).get("on_bridge")]}
    _draw(ax, roads, nothing, lines(MAP_COLORS["roads"], 1.6, 6), nothing)
    _draw(ax, bridges, nothing, lines(MAP_COLORS["bridges"], 1.8, 6), nothing)
    _draw(ax, layers.get("infrastructure"), nothing, nothing, points(MAP_COLORS["infrastructure"], "s", 18, 7))

    # action pins (only those inside the picture; the rest are counted)
    outside, pin_priorities = 0, set()
    for action in data.get("actions") or []:
        lon, lat = action.get("longitude"), action.get("latitude")
        if lon is None or lat is None:
            continue
        if not (view[0] <= lon <= view[1] and view[2] <= lat <= view[3]):
            outside += 1
            continue
        priority = action.get("priority") or "medium"
        pin_priorities.add(priority)
        ax.scatter([lon], [lat], c=PIN_COLORS.get(priority, "#0d6efd"), marker="v", s=55, zorder=8,
                   edgecolors="black", linewidths=0.6)

    ax.set_xlim(view[0], view[1])
    ax.set_ylim(view[2], view[3])
    ax.set_aspect(1.0 / max(np.cos(np.radians((south + north) / 2)), 0.05))      # degrees are not square
    ax.grid(True, color="#cccccc", linewidth=0.3)
    ax.tick_params(labelsize=6)
    ax.set_xlabel("Longitude (degrees)", fontsize=6)
    ax.set_ylabel("Latitude (degrees)", fontsize=6)

    handles = []
    if has_baseline:
        handles += [Patch(facecolor=MAP_COLORS["permanent_water"], label="Permanent water (on the baseline)"),
                    Patch(facecolor=MAP_COLORS["new_flood"], label="New water vs baseline")]
    else:
        handles.append(Patch(facecolor=MAP_COLORS["water"], label="Detected water (no baseline)"))
    handles += [Line2D([0], [0], color=MAP_COLORS["roads"], lw=1.6, label="Flooded road (part)"),
                Line2D([0], [0], color=MAP_COLORS["bridges"], lw=1.8, label="Bridge over the water"),
                Patch(facecolor=MAP_COLORS["farmland"], alpha=0.45, label="Flooded farmland (part)"),
                Patch(facecolor=MAP_COLORS["villages"], alpha=0.4, label="Village"),
                Line2D([0], [0], marker="s", color="w", markerfacecolor=MAP_COLORS["infrastructure"],
                       markersize=5, label="Facility")]
    if pin_priorities:
        handles.append(Line2D([0], [0], marker="v", color="w", markerfacecolor="#888888", markeredgecolor="black",
                              markersize=6, label="Emergency action pin"))
    figure.legend(handles=handles, loc="lower center", ncol=3, fontsize=6, frameon=False,
                  bbox_to_anchor=(0.5, 0.0))

    buffer = io.BytesIO()
    figure.savefig(buffer, format="png")
    return buffer.getvalue(), outside


# ------------------------------------------------------------------ the PDF
def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=19, leading=23, alignment=TA_LEFT,
                                spaceAfter=2),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#555555"),
                              spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12.5, leading=15, spaceBefore=12,
                             spaceAfter=4, textColor=colors.HexColor("#1b2a41")),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=9, leading=12),
        "small": ParagraphStyle("small", parent=base["Normal"], fontSize=7.8, leading=10,
                                textColor=colors.HexColor("#444444")),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontSize=8.5, leading=10.5),
        "cellb": ParagraphStyle("cellb", parent=base["Normal"], fontSize=8.5, leading=10.5, fontName="Helvetica-Bold"),
        "head": ParagraphStyle("head", parent=base["Normal"], fontSize=8.5, leading=10.5, fontName="Helvetica-Bold",
                               textColor=colors.white),
        "bullet": ParagraphStyle("bullet", parent=base["Normal"], fontSize=8.6, leading=11.2, leftIndent=10,
                                 bulletIndent=0, spaceAfter=2),
    }


GRID = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8ccd2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]


def _kv_table(rows, styles, widths=(58 * mm, 116 * mm)):
    """A two-column table of (label, value). Values are already paragraph-safe text."""
    cells = [[Paragraph(escape(label), styles["cellb"]), Paragraph(value, styles["cell"])] for label, value in rows]
    table = Table(cells, colWidths=widths)
    table.setStyle(TableStyle(GRID + [("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef1f5"))]))
    return table


def _grid_table(header, rows, styles, widths, extra=()):
    cells = [[Paragraph(escape(h), styles["head"]) for h in header]]
    cells += [[c if not isinstance(c, str) else Paragraph(c, styles["cell"]) for c in row] for row in rows]
    table = Table(cells, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle(GRID + [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b2a41"))] + list(extra)))
    return table


def _notice(text, styles, background="#fff8e1", border="#e0b400"):
    table = Table([[Paragraph(text, styles["body"])]], colWidths=[174 * mm])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(background)),
                               ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(border)),
                               ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return table


def _level_chip(level, styles):
    label = level.capitalize() if level else "Not classified"
    chip = Table([[Paragraph(f'<font color="{LEVEL_TEXT.get(level, "#000000")}"><b>{escape(label)}</b></font>',
                             styles["body"])]], colWidths=[34 * mm])
    chip.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LEVEL_COLORS.get(level, "#e9ecef"))),
                              ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    chip.hAlign = "LEFT"
    return chip


def day(value, default=NOT_RECORDED) -> str:
    """A calendar date (no time of day), from a date, a datetime or an ISO text."""
    if value is None or value == "":
        return default
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value[:10])
        except ValueError:
            return safe(value)
    try:
        return value.strftime("%d %b %Y")
    except AttributeError:
        return safe(value)


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _section_event(data, styles):
    event, analysis = data.get("event") or {}, data["analysis"]
    place = ", ".join(x for x in (event.get("region_name"), event.get("country")) if x)
    period = day(event.get("start_date"), "start not recorded")
    period += f" to {day(event.get('end_date'))}" if event.get("end_date") else " (no end date)"
    rows = [("Event", f"{para_text(event.get('name'), 'unknown')} (event {analysis['event_id']})"),
            ("Place", para_text(place)), ("Event status", para_text(event.get("status"))),
            ("Event period", escape(period)), ("Description", para_text(event.get("description"), "none"))]
    return [Paragraph("1. Event", styles["h2"]), _kv_table(rows, styles)]


def _section_image(data, styles):
    a = data["analysis"]
    west, south, east, north = a["bounds_wgs84"]
    has_baseline = (a.get("baseline_method") or "none") != "none"
    size = f"{a['width_px']} x {a['height_px']} pixels" if a.get("width_px") and a.get("height_px") else NOT_RECORDED
    rows = [("Analysis", f"{a['analysis_id']} (status: {para_text(a.get('status'))})"),
            ("Image file", para_text(a.get("original_filename"))),
            ("Imagery source", para_text(data.get("source_name"))),
            ("Observation date", escape(moment(data.get("acquired_at")))
             + ("" if data.get("acquired_at") else " (the upload did not include the date the satellite took the image)")),
            ("Analysed at", escape(moment(a.get("created_at")))),
            ("Image size and CRS", f"{escape(size)}, {para_text(a.get('crs'))}"),
            ("Image extent (WGS84)", f"west {west:.4f}, south {south:.4f}, east {east:.4f}, north {north:.4f}"),
            ("Model", f"{para_text(a.get('model_name'))}, threshold {number(a.get('threshold'), 2)}"),
            ("Baseline layer", "JRC water layer: permanent and new water are separated" if has_baseline
             else "none: permanent and new water are not separated")]
    return [Paragraph("2. Image and analysis", styles["h2"]), _kv_table(rows, styles)]


def _section_water(data, styles):
    a = data["analysis"]
    has_baseline = (a.get("baseline_method") or "none") != "none"
    rows = [("Valid image area", f"{number(a.get('valid_area_km2'))} km2"),
            ("Detected surface water (rivers and lakes included)", f"{number(a.get('water_area_km2'))} km2"),
            ("Share of the valid image", f"{number(a.get('water_pct_of_valid'), 1)} %")]
    if has_baseline:
        rows += [("On the baseline layer (permanent water)", f"{number(a.get('permanent_water_area_km2'))} km2"),
                 ("New water relative to the baseline", f"{number(a.get('new_flood_area_km2'))} km2 "
                  f"({number(a.get('new_flood_pct_of_valid'), 1)} % of the valid image)")]
    else:
        rows += [("New water relative to the baseline", "not available (no baseline layer was used)")]
    conf = a.get("mean_confidence")
    rows += [("Average model confidence", (f"{number(float(conf) * 100, 1)} % (the model's certainty, not an accuracy)"
                                           if conf is not None else "not available")),
             ("Water polygons", str(a.get("zone_count", 0)))]
    out = [Paragraph("3. Detected water", styles["h2"]), _kv_table(rows, styles)]
    for warning in a.get("warnings") or []:
        out += [Spacer(1, 3), _notice(f"Warning from the analysis: {para_text(warning)}", styles)]
    return out


def _section_map(data, styles):
    png, outside = render_map(data)
    image = Image(io.BytesIO(png), width=174 * mm, height=174 * mm * 4.9 / 6.6)
    note = ("Flood extent map drawn from the stored results; no base map is included. Dashed rectangle: the "
            "analysed image. Village, road, farmland and facility data from OpenStreetMap contributors. ")
    if (data.get("impact") or {}).get("layers") is None:
        note += "Impact has not been computed, so only the detected water is drawn. "
    if outside:
        note += f"{outside} emergency action pin(s) of this event lie outside this view and are not shown."
    return [KeepTogether([Paragraph("4. Flood extent map", styles["h2"]), image,
                          Paragraph(escape(note), styles["small"])])]


def _section_severity(data, styles):
    severity, a = data["severity"], data["analysis"]
    stored = a.get("severity")
    rows = []
    for ind in severity["indicators"]:
        value = ind["value"]
        if value is None:
            shown, level = "not computed", "-"
        else:
            unit = f" {ind['unit']}" if ind.get("unit") else ""
            digits = 0 if ind["key"] in ("villages", "facilities") else 2
            shown = f"{number(value, digits)}{unit}"
            if ind.get("detail"):
                shown += f" ({escape(ind['detail'])})"
            level = ind["level"].capitalize() if ind.get("level") else "-"
        t = ind["thresholds"]
        limits = f"moderate from {t['moderate']:g}, high from {t['high']:g}, severe from {t['severe']:g}"
        rows.append([para_text(ind["label"]), shown, level, limits])
    table = _grid_table(["Indicator", "Value", "Level", "Limits"], rows, styles,
                        [62 * mm, 32 * mm, 22 * mm, 58 * mm])

    out = [Paragraph("5. Severity (provisional rules)", styles["h2"]), _level_chip(severity["level"], styles),
           Spacer(1, 4)]
    if stored is None:
        out.append(Paragraph("Not saved yet: this is the level worked out now from the stored results.",
                             styles["small"]))
    elif stored == severity["level"]:
        out.append(Paragraph(f"Saved classification: {para_text(stored.capitalize())} (up to date).", styles["small"]))
    else:
        out.append(Paragraph(f"Saved classification: {para_text(stored.capitalize())}, which is out of date. "
                             f"The level above is worked out from the current results.", styles["small"]))
    if not severity["impact_included"]:
        out += [Spacer(1, 3), _notice("Impact has not been computed, so only the water area counts towards this "
                                      "level. The real level may be higher.", styles)]
    out += [Spacer(1, 4), table, Spacer(1, 3), Paragraph(para_text(severity["note"]), styles["small"]),
            Paragraph(para_text(
                "A hospital, clinic, police station or fire station inside the flooded area counts as high on its "
                "own; schools, colleges and shelters count by number."), styles["small"])]
    return out


def _name(props, fallback):
    return para_text(props.get("name"), fallback)


def _section_impact(data, styles):
    impact = data.get("impact") or {}
    summary = impact.get("summary")
    heading = Paragraph("6. Infrastructure impact (estimate)", styles["h2"])
    if not summary or not summary.get("last_computed_at"):
        return [KeepTogether([heading, _notice(
            "Impact has not been computed for this analysis, so no figures are shown here. This does not mean "
            "that nothing was affected. An analyst can compute the impact on the analysis page, after which this "
            "report can be downloaded again.", styles)])]

    layers = impact.get("layers") or {}
    v, r, f, i = summary["villages"], summary["roads"], summary["farmland"], summary["infrastructure"]
    intro = Paragraph(
        f"Compared against: {para_text(summary.get('compared_against'))}. Impact last computed "
        f"{escape(moment(summary.get('last_computed_at')))}. Only features mapped in OpenStreetMap are counted, so "
        f"these figures are lower bounds.", styles["body"])
    rows = [["Villages", f"{v['inside']} inside the flooded area, {v['near']} near it"],
            ["Flooded roads (bridges excluded)", f"{plural(r['count'], 'road')}, {number(r['flooded_length_km'], 3)} km flooded"],
            ["Bridges over the detected water (not counted as flooded)",
             f"{plural(r['bridges']['count'], 'bridge')}, {number(r['bridges']['length_km'], 3)} km lie over the water"],
            ["Farmland", f"{plural(f['count'], 'area')}, {number(f['flooded_area_km2'], 3)} km2 flooded"],
            ["Facilities", f"{i['inside']} inside the flooded area, {i['near']} near it"]]
    coverage = data.get("coverage") or {}
    if coverage.get("level") in ("none", "partial"):
        coverage_block = [_notice(escape(str(coverage.get("message", ""))), styles), Spacer(1, 4)]
    elif coverage.get("message"):
        coverage_block = [Paragraph(escape(str(coverage["message"])), styles["small"]), Spacer(1, 4)]
    else:
        coverage_block = []
    out = [KeepTogether([heading, intro, Spacer(1, 4), *coverage_block,
                         _grid_table(["Layer", "Estimate"], rows, styles, [74 * mm, 100 * mm])])]

    # facilities by type
    by_category = i.get("by_category") or {}
    if by_category:
        cat_rows = [[para_text(name.replace("_", " ").capitalize()), str(c.get("inside", 0)), str(c.get("near", 0))]
                    for name, c in sorted(by_category.items())]
        out += [Spacer(1, 5), Paragraph("Facilities by type", styles["cellb"]), Spacer(1, 2),
                _grid_table(["Type", "Inside", "Near"], cat_rows, styles, [74 * mm, 30 * mm, 30 * mm])]

    def listing(title, items, header, row_of, widths, empty):
        block = [Spacer(1, 6), Paragraph(title, styles["cellb"]), Spacer(1, 2)]
        if not items:
            block.append(Paragraph(empty, styles["small"]))
            return block
        shown = [row_of(p) for p in items[:MAX_LIST]]
        block.append(_grid_table(header, shown, styles, widths))
        if len(items) > MAX_LIST:
            block.append(Paragraph(f"... and {len(items) - MAX_LIST} more (see the web page).", styles["small"]))
        return block

    props = lambda name: [(x.get("properties") or {}) for x in (layers.get(name) or {}).get("features", [])]   # noqa: E731
    villages = sorted(props("villages"), key=lambda p: (p.get("relation") != "inside", safe(p.get("name"), "~")))
    out += listing("Villages", villages, ["Name", "Relation", "Distance (m)"],
                   lambda p: [_name(p, "(unnamed)"), para_text(p.get("relation")),
                              number(p.get("distance_m"), 0, "-")],
                   [100 * mm, 38 * mm, 36 * mm], "No village was found inside or near the flooded area.")

    all_roads = props("roads")
    roads = sorted([p for p in all_roads if not p.get("on_bridge")],
                   key=lambda p: -(float(p.get("flooded_length_km") or 0)))
    out += listing("Flooded roads (bridges excluded)", roads, ["Name", "Road type", "Flooded length (km)"],
                   lambda p: [_name(p, "(unnamed road)"), para_text(p.get("category")),
                              number(p.get("flooded_length_km"), 3)],
                   [90 * mm, 40 * mm, 44 * mm], "No flooded road was found.")

    bridges = [p for p in all_roads if p.get("on_bridge")]
    out += listing("Bridges over the detected water", bridges, ["Name", "OpenStreetMap reference",
                                                                 "Length over water (km)"],
                   lambda p: [_name(p, "(unnamed bridge)"), para_text(p.get("source_ref")),
                              number(p.get("flooded_length_km"), 3)],
                   [74 * mm, 56 * mm, 44 * mm], "No bridge over the detected water was found.")
    if bridges:
        out.append(Paragraph("A bridge crosses above the detected water. It is not automatically a flooded road "
                             "and is not counted in the flooded road length.", styles["small"]))

    facilities = sorted(props("infrastructure"), key=lambda p: (p.get("relation") != "inside",
                                                                 float(p.get("distance_m") or 0)))
    out += listing("Facilities", facilities, ["Name", "Type", "Relation", "Distance (m)"],
                   lambda p: [_name(p, "(unnamed)"), para_text(p.get("category")), para_text(p.get("relation")),
                              number(p.get("distance_m"), 0, "-")],
                   [70 * mm, 40 * mm, 32 * mm, 32 * mm], "No facility was found inside or near the flooded area.")
    return out


def _section_actions(data, styles):
    actions = data.get("actions") or []
    event = data.get("event") or {}
    out = [Paragraph("7. Emergency response actions of this event", styles["h2"]),
           Paragraph(f"Actions belong to the event ({para_text(event.get('name'), 'event ' + str(data['analysis']['event_id']))}), "
                     f"not to a single analysis, so every analysis of the event lists the same actions.",
                     styles["small"]), Spacer(1, 3)]
    if not actions:
        out.append(Paragraph("No emergency actions have been recorded for this event.", styles["body"]))
        return out
    rows = []
    for a in actions[:MAX_LIST * 2]:
        pin = "yes" if a.get("longitude") is not None else "no"
        rows.append([para_text(a.get("title")), para_text(TYPE_LABEL.get(a.get("action_type"), a.get("action_type"))),
                     para_text((a.get("priority") or "").capitalize()),
                     para_text(STATUS_LABEL.get(a.get("status"), a.get("status"))),
                     escape(moment(a.get("due_at"), "-")), para_text(a.get("assigned_to_username"), "-"), pin])
    out.append(_grid_table(["Action", "Type", "Priority", "Status", "Due", "Assigned to", "Pin"], rows, styles,
                           [48 * mm, 27 * mm, 16 * mm, 20 * mm, 33 * mm, 20 * mm, 10 * mm]))
    if len(actions) > MAX_LIST * 2:
        out.append(Paragraph(f"... and {len(actions) - MAX_LIST * 2} more (see the event page).", styles["small"]))
    return out


def _section_limits(styles):
    out = [Paragraph("8. Limitations and reliability", styles["h2"])]
    for text in LIMITATIONS:
        out.append(Paragraph(escape(text), styles["bullet"], bulletText="-"))
    return out


def _page_footer(analysis_id):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(18 * mm, 10 * mm, f"GeoFlood AI | Analysis {analysis_id} | model estimate from Sentinel-1 "
                                            f"radar, not an official flood map")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def build_report(data, *, compress=True) -> bytes:
    """
    data = {
      generated_at, generated_by,
      analysis   : the analysis as the API returns it,
      event      : {name, region_name, country, status, start_date, end_date, description},
      source_name, acquired_at,
      zones      : GeoJSON FeatureCollection of the flood polygons,
      impact     : {summary: impact summary or None, layers: {villages, roads, farmland, infrastructure}} or None,
      severity   : the result of services.severity.classify(),
      actions    : the event's emergency actions,
    }
    Returns the PDF as bytes. compress=False keeps the text readable inside the file (used by the tests).
    """
    styles = _styles()
    analysis = data["analysis"]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=f"GeoFlood AI analysis {analysis['analysis_id']} report",
                            author="GeoFlood AI", pageCompression=1 if compress else 0)

    who = data.get("generated_by")
    story = [Paragraph(escape(TITLE), styles["title"]),
             Paragraph(f"Analysis {analysis['analysis_id']} | generated {escape(moment(data.get('generated_at')))}"
                       + (f" by {para_text(who)}" if who else ""), styles["sub"]),
             _notice("<b>How to read this report.</b> It is a model estimate from Sentinel-1 radar imagery. Detected "
                     "water is not confirmed flooding, infrastructure figures are estimates from OpenStreetMap, and "
                     "the severity level follows provisional rules. Section 8 lists the limitations.", styles,
                     "#e8f1fb", "#6ea8dc")]
    story += _section_event(data, styles)
    story += _section_image(data, styles)
    story += _section_water(data, styles)
    story += _section_map(data, styles)
    story += _section_severity(data, styles)
    story += _section_impact(data, styles)
    story += _section_actions(data, styles)
    story += _section_limits(styles)

    footer = _page_footer(analysis["analysis_id"])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
