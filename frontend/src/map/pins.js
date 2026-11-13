import L from "leaflet";
import { CLOSED, PRIORITY_COLOR } from "../actions.js";
import { actionPopup } from "./actionPopup.js";

const FALLBACK_COLOR = "#6c757d";

/** A circle coloured by priority; faded once the action is completed or cancelled. */
export function pinToLayer(feature, latlng) {
  const { priority, status } = feature?.properties || {};
  return L.circleMarker(latlng, {
    radius: 9,
    color: "#ffffff",
    weight: 2,
    fillColor: PRIORITY_COLOR[priority] || FALLBACK_COLOR,
    fillOpacity: CLOSED.has(status) ? 0.35 : 0.95,
  });
}

export function onEachPin(feature, layer) {
  layer.bindPopup(actionPopup(feature?.properties));
}
