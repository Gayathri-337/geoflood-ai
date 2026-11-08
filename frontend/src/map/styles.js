import L from "leaflet";
import { COLORS } from "./layers.js";

export function zoneStyle(feature) {
  const type = feature?.properties?.zone_type;
  const color =
    type === "new_flood" ? COLORS.newFlood : type === "permanent_water" ? COLORS.permanentWater : COLORS.water;
  return { color, weight: 1, fillColor: color, fillOpacity: 0.45 };
}



export function roadStyle(feature) {
  if (feature?.properties?.on_bridge) {
    // a bridge over the detected water: shown, but not counted as flooded
    return { color: COLORS.bridges, weight: 5, opacity: 0.95, dashArray: "8 6" };
  }
  return { color: COLORS.roads, weight: 5, opacity: 0.95 };
}

export function areaStyle(layerKey) {
  const color = COLORS[layerKey];
  return { color, weight: 2, fillColor: color, fillOpacity: 0.35 };
}

/** Points are drawn as circles: big and solid inside the flooded area, small and faded when only near it. */
export function pointToLayerFor(layerKey) {
  const color = COLORS[layerKey];
  return (feature, latlng) => {
    const inside = feature?.properties?.relation === "inside";
    return L.circleMarker(latlng, {
      pane: layerKey,
      radius: inside ? 8 : 6,
      color: "#ffffff",
      weight: 1.5,
      fillColor: color,
      fillOpacity: inside ? 0.95 : 0.45,
    });
  };
}
