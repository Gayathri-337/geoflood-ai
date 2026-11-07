/** [west, south, east, north] in degrees -> Leaflet's [[south, west], [north, east]], or null if unusable. */
export function toLeafletBounds(bbox) {
  if (!Array.isArray(bbox) || bbox.length !== 4) return null;
  const [west, south, east, north] = bbox;
  if (![west, south, east, north].every((v) => typeof v === "number" && Number.isFinite(v))) return null;
  if (west >= east || south >= north) return null;
  if (west < -180 || east > 180 || south < -90 || north > 90) return null;
  return [
    [south, west],
    [north, east],
  ];
}
