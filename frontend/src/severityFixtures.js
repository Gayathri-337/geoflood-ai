const NOTE =
  "Provisional rules chosen for this project: not an official standard and not calibrated against damage data.";

export const SEVERITY = {
  analysis_id: 2,
  level: "high",
  driven_by: ["facilities"],
  impact_included: true,
  stored_severity: null,
  note: NOTE,
  indicators: [
    { key: "area_pct", label: "Share of the image covered by new water (vs baseline)", unit: "%", value: 2.098, level: "moderate", thresholds: { moderate: 2, high: 10, severe: 25 } },
    { key: "road_km", label: "Flooded road length (bridges excluded)", unit: "km", value: 0, level: "low", thresholds: { moderate: 0.5, high: 2, severe: 5 } },
    { key: "villages", label: "Villages inside the flooded area", unit: "", value: 0, level: "low", thresholds: { moderate: 1, high: 3, severe: 6 } },
    { key: "farmland_km2", label: "Flooded farmland area", unit: "km²", value: 0, level: "low", thresholds: { moderate: 0.1, high: 1, severe: 5 } },
    { key: "facilities", label: "Facilities inside the flooded area", unit: "", value: 1, level: "high", thresholds: { moderate: null, high: 1, severe: 3 } },
  ],
};

export const SEVERITY_NO_IMPACT = {
  ...SEVERITY,
  level: "moderate",
  driven_by: ["area_pct"],
  impact_included: false,
  indicators: SEVERITY.indicators.map((i) => (i.key === "area_pct" ? i : { ...i, value: null, level: null })),
};
