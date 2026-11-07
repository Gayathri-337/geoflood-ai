import "leaflet/dist/leaflet.css";
import { GeoJSON, MapContainer, Pane, Rectangle, TileLayer } from "react-leaflet";
import { toLeafletBounds } from "./bounds.js";
import { PANE_Z } from "./layers.js";
import { popupFor } from "./popups.js";
import { areaStyle, pointToLayerFor, roadStyle, zoneStyle } from "./styles.js";

const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

// Built once, so the map libraries do not see new functions on every render.
const STYLE_FOR = {
  zones: zoneStyle,
  roads: roadStyle,
  farmland: () => areaStyle("farmland"),
  villages: () => areaStyle("villages"),
  infrastructure: () => areaStyle("infrastructure"),
};
const POINTS_FOR = { villages: pointToLayerFor("villages"), infrastructure: pointToLayerFor("infrastructure") };
const ON_EACH_FEATURE = Object.fromEntries(
  Object.keys(STYLE_FOR).map((key) => [key, (feature, layer) => layer.bindPopup(popupFor(key, feature.properties))]),
);

/**
 * bounds  : [west, south, east, north] of the analysed image
 * layers  : { zones, roads, villages, farmland, infrastructure } GeoJSON FeatureCollections (or null)
 * visible : { zones: true, ... } which layers to draw
 * version : changes whenever the data changes, so the layers are redrawn
 */
export default function AnalysisMap({ bounds, layers, visible, version = 0 }) {
  const leafletBounds = toLeafletBounds(bounds);
  if (!leafletBounds) {
    return <div className="alert alert-warning m-3">This analysis has no usable map position.</div>;
  }

  return (
    <MapContainer
      bounds={leafletBounds}
      boundsOptions={{ padding: [20, 20] }}
      scrollWheelZoom
      style={{ height: "100%", width: "100%" }}
    >
      <TileLayer attribution={ATTRIBUTION} url={TILE_URL} maxZoom={19} />
      <Rectangle
        bounds={leafletBounds}
        pathOptions={{ color: "#444444", weight: 1, dashArray: "6 4", fill: false, interactive: false }}
      />
      {Object.keys(PANE_Z).map((key) => {
        const data = layers?.[key];
        if (!visible?.[key] || !data || !Array.isArray(data.features) || data.features.length === 0) return null;
        return (
          <Pane key={`${key}-${version}`} name={key} style={{ zIndex: PANE_Z[key] }}>
            <GeoJSON
              data={data}
              style={STYLE_FOR[key]}
              pointToLayer={POINTS_FOR[key]}
              onEachFeature={ON_EACH_FEATURE[key]}
            />
          </Pane>
        );
      })}
    </MapContainer>
  );
}
