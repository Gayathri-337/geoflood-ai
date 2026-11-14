// Flood progression (Phase 29b): small helpers for the Event page panel. No chart library is used.

export const DIRECTION_TEXT = {
  more: "More detected water",
  less: "Less detected water",
  similar: "About the same",
};

export const REASON_TITLE = {
  no_date: "No observation date",
  only_one_date: "Only one date for this area",
  same_date_duplicate: "Same image and date analysed again",
};

export function directionText(direction) {
  return DIRECTION_TEXT[direction] || "Not available";
}

/** "2026-10-27" for a midnight (UTC) value, otherwise "2026-10-27 05:30 UTC". */
export function formatObserved(iso) {
  const date = new Date(iso);
  if (!iso || Number.isNaN(date.getTime())) return "–";
  const day = date.toISOString().slice(0, 10);
  const time = date.toISOString().slice(11, 16);
  return time === "00:00" ? day : `${day} ${time} UTC`;
}

/** "+1.70 km²", "−0.40 km²", "0.00 km²" or "–". */
export function formatDelta(km2) {
  if (km2 === null || km2 === undefined) return "–";
  const rounded = Math.abs(km2).toFixed(2);
  if (Number(rounded) === 0) return "0.00 km²";
  return `${km2 > 0 ? "+" : "−"}${rounded} km²`;
}

export function formatPctChange(pct) {
  if (pct === null || pct === undefined) return "–";
  const rounded = Math.abs(pct).toFixed(1);
  if (Number(rounded) === 0) return "0.0%";
  return `${pct > 0 ? "+" : "−"}${rounded}%`;
}

export function formatDays(days) {
  if (days === null || days === undefined) return "–";
  const value = Number(days);
  const text = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return `${text} day${value === 1 ? "" : "s"}`;
}

const niceMax = (value) => {
  if (!(value > 0)) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 4, 5, 8, 10].find((m) => m * power >= value);
  return step * power;
};

/**
 * Coordinates for a hand-drawn SVG line chart of one series.
 * x follows the real dates (not equal spacing); y starts at 0 km² so the size of a change is not exaggerated.
 * Points without a water area are left out.
 */
export function chartModel(series, { width = 520, height = 240 } = {}) {
  const margin = { top: 16, right: 20, bottom: 40, left: 52 };
  const usable = (series?.points || []).filter(
    (p) => p.water_area_km2 !== null && p.water_area_km2 !== undefined && p.observed_at,
  );
  if (usable.length < 2) return null;

  const times = usable.map((p) => new Date(p.observed_at).getTime());
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  if (!(t1 > t0)) return null;
  const top = niceMax(Math.max(...usable.map((p) => p.water_area_km2)));

  const w = width - margin.left - margin.right;
  const h = height - margin.top - margin.bottom;
  const x = (t) => margin.left + ((t - t0) / (t1 - t0)) * w;
  const y = (v) => margin.top + h - (v / top) * h;

  const points = usable.map((p, i) => ({
    analysis_id: p.analysis_id,
    x: x(times[i]),
    y: y(p.water_area_km2),
    area: p.water_area_km2,
    label: formatObserved(p.observed_at),
  }));
  const digits = top >= 4 ? 0 : top >= 1 ? 1 : top >= 0.1 ? 2 : 3;
  const yTicks = [0, 0.5, 1].map((f) => ({ y: y(top * f), label: (top * f).toFixed(digits) }));
  const xTicks = [
    { x: points[0].x, label: points[0].label, anchor: "start" },
    { x: points[points.length - 1].x, label: points[points.length - 1].label, anchor: "end" },
  ];
  return {
    width,
    height,
    margin,
    points,
    path: points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" "),
    yTicks,
    xTicks,
    baselineY: y(0),
    right: margin.left + w,
  };
}
