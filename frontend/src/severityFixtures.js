const NOTE =
  "Provisional rules chosen for this project: not an official standard and not calibrated against damage data.";
const FACILITY_NOTE =
  "A hospital, clinic, police station or fire station inside counts as high on its own. Other facilities (schools, colleges, shelters) count by number.";

export const SEVERITY = {
  analysis_id: 2,
  level: "high",
  driven_by: ["facilities"],
  impact_included: true,
  stored_severity: null,
  note: NOTE,
  indicators: [
    { key: "area_pct", label: "Share of the image covered by new water (vs baseline)", unit: "%", value: 2.098, level: "moderate", thresholds: { moderate: 2, high: 10, severe: 25 }, detail: null, note: null },
    { key: "road_km", label: "Flooded road length (bridges excluded)", unit: "km", value: 0, level: "low", thresholds: { moderate: 0.5, high: 2, severe: 5 }, detail: null, note: null },
    { key: "villages", label: "Villages inside the flooded area", unit: "", value: 0, level: "low", thresholds: { moderate: 1, high: 3, severe: 6 }, detail: null, note: null },
    { key: "farmland_km2", label: "Flooded farmland area", unit: "km²", value: 0, level: "low", thresholds: { moderate: 0.1, high: 1, severe: 5 }, detail: null, note: null },
    { key: "facilities", label: "Facilities inside the flooded area", unit: "", value: 1, level: "high", thresholds: { moderate: 1, high: 2, severe: 3 }, detail: "1 critical", note: FACILITY_NOTE },
  ],
};

export const SEVERITY_NO_IMPACT = {
  ...SEVERITY,
  level: "moderate",
  driven_by: ["area_pct"],
  impact_included: false,
  indicators: SEVERITY.indicators.map((i) => (i.key === "area_pct" ? i : { ...i, value: null, level: null, detail: null })),
};

// the same card with a rule that has no 'moderate' step, to check the card copes with a skipped step
export const SEVERITY_SKIPPED_STEP = {
  ...SEVERITY,
  indicators: SEVERITY.indicators.map((i) =>
    i.key === "facilities" ? { ...i, thresholds: { moderate: null, high: 1, severe: 3 }, detail: null, note: null } : i,
  ),
};