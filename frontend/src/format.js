const km2Format = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const intFormat = new Intl.NumberFormat("en-IN");

const isMissing = (value) => value === null || value === undefined;

export function formatKm2(value) {
  return isMissing(value) ? "–" : km2Format.format(value);
}

export function formatInt(value) {
  return isMissing(value) ? "–" : intFormat.format(value);
}

export function formatDate(iso) {
  if (!iso) return "–";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "–" : date.toLocaleString();
}
