import "leaflet/dist/leaflet.css";
import { useEffect } from "react";
import { CircleMarker, GeoJSON, MapContainer, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { onEachPin, pinToLayer } from "./pins.js";
import { ATTRIBUTION, TILE_URL } from "./tiles.js";

/** Turns map clicks into a picked position while `enabled`, and shows a crosshair cursor. */
function ClickToPick({ enabled, onPick }) {
  const map = useMap();
  useEffect(() => {
    const container = map.getContainer();
    container.style.cursor = enabled ? "crosshair" : "";
    return () => {
      container.style.cursor = "";
    };
  }, [map, enabled]);
  useMapEvents({
    click(event) {
      if (enabled && onPick) onPick(event.latlng.lng, event.latlng.lat);
    },
  });
  return null;
}

/**
 * bounds  : Leaflet bounds [[south, west], [north, east]] (only used when the map is first drawn)
 * pins    : GeoJSON FeatureCollection of actions that have a location
 * picking : true while the user is choosing a pin position
 * picked  : { longitude, latitude } of the position chosen so far, or null
 * onPick  : called with (longitude, latitude) when the map is clicked while picking
 * version : changes whenever the pins change, so they are redrawn
 */
export default function EventMap({ bounds, pins, picking = false, picked = null, onPick, version = 0 }) {
  const hasPins = pins && Array.isArray(pins.features) && pins.features.length > 0;
  return (
    <MapContainer
      bounds={bounds}
      boundsOptions={{ padding: [30, 30] }}
      scrollWheelZoom
      style={{ height: "100%", width: "100%" }}
    >
      <TileLayer attribution={ATTRIBUTION} url={TILE_URL} maxZoom={19} />
      <ClickToPick enabled={picking} onPick={onPick} />
      {hasPins && <GeoJSON key={version} data={pins} pointToLayer={pinToLayer} onEachFeature={onEachPin} />}
      {picked && (
        <CircleMarker
          center={[picked.latitude, picked.longitude]}
          radius={12}
          pathOptions={{ color: "#212529", weight: 3, fill: false, dashArray: "4 3", interactive: false }}
        />
      )}
    </MapContainer>
  );
}
