import { toLeafletBounds } from "./bounds.js";

// Assam and the surrounding region: shown when an event has no analyses and no pins yet
export const DEFAULT_BOUNDS = [
  [24.0, 89.5],
  [28.5, 96.5],
];
const MIN_SPAN = 0.01; // degrees; a smaller box (a single pin) is widened so the map is not zoomed in fully
const PAD = 0.02;

function pinCoordinates(feature) {
  const c = feature?.geometry?.coordinates;
  if (!Array.isArray(c) || c.length < 2) return null;
  const [lon, lat] = c;
  const ok = [lon, lat].every((v) => typeof v === "number" && Number.isFinite(v));
  return ok && Math.abs(lon) <= 180 && Math.abs(lat) <= 90 ? [lon, lat] : null;
}

/** Leaflet bounds [[south, west], [north, east]] that show every analysis footprint and every action pin. */
export function eventBounds(analyses, pins) {
  const boxes = [];
  for (const analysis of analyses || []) {
    if (toLeafletBounds(analysis?.bounds_wgs84)) boxes.push(analysis.bounds_wgs84);
  }
  for (const feature of pins?.features || []) {
    const point = pinCoordinates(feature);
    if (point) boxes.push([point[0], point[1], point[0], point[1]]);
  }
  if (boxes.length === 0) return DEFAULT_BOUNDS;

  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
  for (const [w, s, e, n] of boxes) {
    west = Math.min(west, w);
    south = Math.min(south, s);
    east = Math.max(east, e);
    north = Math.max(north, n);
  }
  if (east - west < MIN_SPAN) {
    west -= PAD;
    east += PAD;
  }
  if (north - south < MIN_SPAN) {
    south -= PAD;
    north += PAD;
  }
  return [
    [south, west],
    [north, east],
  ];
}
