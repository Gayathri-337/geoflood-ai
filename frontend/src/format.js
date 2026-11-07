const intFormat = new Intl.NumberFormat("en-IN");

const isMissing = (value) => value === null || value === undefined;

export function formatKm2(value, digits = 2) {
  if (isMissing(value)) return "–";
  return new Intl.NumberFormat("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

export function formatInt(value) {
  return isMissing(value) ? "–" : intFormat.format(value);
}

export function formatPercent(value, digits = 1) {
  return isMissing(value) ? "–" : `${Number(value).toFixed(digits)}%`;
}

/** A length given in kilometres, shown in metres below 1 km. */
export function formatLength(km) {
  if (isMissing(km)) return "–";
  const meters = Math.round(Number(km) * 1000);
  return meters < 1000 ? `${meters} m` : `${Number(km).toFixed(2)} km`;
}

export function formatMeters(meters) {
  return isMissing(meters) ? "–" : `${Math.round(Number(meters))} m`;
}

export function formatDate(iso) {
  if (!iso) return "–";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "–" : date.toLocaleString();
}