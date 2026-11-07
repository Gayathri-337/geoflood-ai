import { formatInt, formatKm2, formatLength, formatMeters, formatPercent } from "../format.js";

/** A popup made of plain text nodes. Names come from OpenStreetMap, so nothing here is ever treated as HTML. */
export function buildPopup(title, rows) {
  const root = document.createElement("div");
  const heading = document.createElement("strong");
  heading.textContent = title;
  root.appendChild(heading);
  for (const [label, value] of rows) {
    const line = document.createElement("div");
    line.textContent = `${label}: ${value}`;
    root.appendChild(line);
  }
  return root;
}

const text = (value, fallback = "–") => (value === null || value === undefined || value === "" ? fallback : String(value));
const nameOr = (props, fallback) => text(props.name && String(props.name).trim(), fallback);

function relationText(props) {
  if (props.relation === "inside") return "Inside the flooded area";
  if (props.relation === "near") return `Near: ${formatMeters(props.distance_m)} from the flooded area`;
  return "–";
}

const ZONE_TITLES = {
  permanent_water: "Permanent water (on the baseline)",
  new_flood: "New water vs baseline",
  water: "Detected water",
};

function zonePopup(p) {
  const confidence =
    p.mean_confidence === null || p.mean_confidence === undefined ? "–" : formatPercent(p.mean_confidence * 100);
  return buildPopup(ZONE_TITLES[p.zone_type] || "Water zone", [
    ["Area", `${formatKm2(p.area_km2, 4)} km²`],
    ["Pixels", formatInt(p.n_pixels)],
    ["Average model confidence", confidence],
  ]);
}

function roadPopup(p) {
  return buildPopup(nameOr(p, "Unnamed road"), [
    ["Road class", text(p.category)],
    ["Flooded length", formatLength(p.flooded_length_km)],
    ["Share of this mapped road", formatPercent(p.flooded_pct)],
    ["OpenStreetMap", text(p.source_ref)],
  ]);
}

function farmlandPopup(p) {
  return buildPopup(nameOr(p, "Unnamed farmland"), [
    ["Type", text(p.category)],
    ["Flooded area", `${formatKm2(p.flooded_area_km2, 4)} km²`],
    ["Share of this field", formatPercent(p.flooded_pct)],
    ["OpenStreetMap", text(p.source_ref)],
  ]);
}

function villagePopup(p) {
  const rows = [
    ["Type", text(p.category)],
    ["Position", relationText(p)],
  ];
  if (p.flooded_area_km2 !== null && p.flooded_area_km2 !== undefined) {
    rows.push(["Flooded part", `${formatKm2(p.flooded_area_km2, 4)} km² (${formatPercent(p.flooded_pct)})`]);
  }
  rows.push(["OpenStreetMap", text(p.source_ref)]);
  return buildPopup(nameOr(p, "Unnamed place"), rows);
}

function infrastructurePopup(p) {
  return buildPopup(nameOr(p, "Unnamed facility"), [
    ["Type", text(p.category)],
    ["Position", relationText(p)],
    ["OpenStreetMap", text(p.source_ref)],
  ]);
}

const BUILDERS = {
  zones: zonePopup,
  roads: roadPopup,
  farmland: farmlandPopup,
  villages: villagePopup,
  infrastructure: infrastructurePopup,
};

export function popupFor(layerKey, properties) {
  const build = BUILDERS[layerKey];
  return build ? build(properties || {}) : buildPopup("Feature", []);
}
