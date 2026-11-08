/** Colours, names and stacking order of the map layers, shared by the map, the legend and the popups. */
export const COLORS = {
  permanentWater: "#1f78b4", // blue
  newFlood: "#e6550d", // orange
  water: "#2b8cbe", // used when an analysis has no baseline
  farmland: "#33a02c",
  roads: "#d7191c",
  villages: "#6a3d9a",
  infrastructure: "#111111",
  bridges: "#6b7280", // grey: a bridge over the detected water
};

// Stacking order on the map: a higher number is drawn above a lower one.
export const PANE_Z = { farmland: 410, zones: 420, roads: 430, villages: 440, infrastructure: 450 };

export const LAYER_KEYS = ["zones", "roads", "villages", "farmland", "infrastructure"]; // order in the side panel
export const IMPACT_LAYERS = ["villages", "roads", "farmland", "infrastructure"]; // names used by the API

export const LAYER_LABELS = {
  zones: "Detected water zones",
  roads: "Affected roads (flooded part)",
  villages: "Affected villages",
  farmland: "Affected farmland (flooded part)",
  infrastructure: "Affected facilities",
};