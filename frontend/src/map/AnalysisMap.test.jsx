import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ANALYSIS, FARMLAND, INFRASTRUCTURE, ROADS, VILLAGES, ZONES } from "../mapFixtures.js";
import AnalysisMap from "./AnalysisMap.jsx";

// The map library is replaced by simple elements, so these tests check WHAT is drawn, not how it looks.
vi.mock("react-leaflet", async () => {
  const React = await import("react");
  const h = React.createElement;
  return {
    MapContainer: ({ children, bounds }) => h("div", { "data-testid": "map", "data-bounds": JSON.stringify(bounds) }, children),
    TileLayer: ({ attribution, url }) => h("div", { "data-testid": "tiles", "data-attribution": attribution, "data-url": url }),
    Rectangle: ({ bounds }) => h("div", { "data-testid": "footprint", "data-bounds": JSON.stringify(bounds) }),
    Pane: ({ name, style, children }) => h("div", { "data-testid": `pane-${name}`, "data-z": String(style.zIndex) }, children),
    GeoJSON: ({ data }) => h("div", { "data-testid": "geojson", "data-count": String(data.features.length) }),
  };
});

const LAYERS = { zones: ZONES, roads: ROADS, villages: VILLAGES, farmland: FARMLAND, infrastructure: INFRASTRUCTURE };
const ALL = { zones: true, roads: true, villages: true, farmland: true, infrastructure: true };

describe("AnalysisMap", () => {
  it("uses OpenStreetMap tiles and shows the attribution", () => {
    render(<AnalysisMap bounds={ANALYSIS.bounds_wgs84} layers={LAYERS} visible={ALL} />);
    const tiles = screen.getByTestId("tiles");
    expect(tiles.dataset.url).toBe("https://tile.openstreetmap.org/{z}/{x}/{y}.png");
    expect(tiles.dataset.attribution).toContain("OpenStreetMap");
    expect(tiles.dataset.attribution).toContain("openstreetmap.org/copyright");
  });

  it("fits the map to the image (latitude first) and outlines the image", () => {
    render(<AnalysisMap bounds={ANALYSIS.bounds_wgs84} layers={LAYERS} visible={ALL} />);
    const expected = [
      [26.538377, 93.735237],
      [26.584371, 93.781231],
    ];
    expect(JSON.parse(screen.getByTestId("map").dataset.bounds)).toEqual(expected);
    expect(JSON.parse(screen.getByTestId("footprint").dataset.bounds)).toEqual(expected);
  });

  it("draws each visible layer in its own pane, stacked in the right order", () => {
    // an empty collection draws nothing, so give farmland any non-empty collection for this check
    render(<AnalysisMap bounds={ANALYSIS.bounds_wgs84} layers={{ ...LAYERS, farmland: ZONES }} visible={ALL} />);
    const z = (name) => Number(screen.getByTestId(`pane-${name}`).dataset.z);
    expect(z("zones")).toBeGreaterThan(z("farmland"));
    expect(z("roads")).toBeGreaterThan(z("zones"));
    expect(z("villages")).toBeGreaterThan(z("roads"));
    expect(z("infrastructure")).toBeGreaterThan(z("villages"));
    expect(screen.getByTestId("pane-zones").querySelector("[data-count]").dataset.count).toBe("2");
    expect(screen.getByTestId("pane-roads").querySelector("[data-count]").dataset.count).toBe("2");
  });

  it("draws nothing for an empty collection or missing data", () => {
    render(<AnalysisMap bounds={ANALYSIS.bounds_wgs84} layers={{ ...LAYERS, zones: null }} visible={ALL} />);
    expect(screen.queryByTestId("pane-farmland")).toBeNull(); // the farmland collection is empty
    expect(screen.queryByTestId("pane-zones")).toBeNull(); // no data at all
    expect(screen.getByTestId("pane-roads")).toBeInTheDocument();
  });

  it("does not draw layers that are switched off", () => {
    render(<AnalysisMap bounds={ANALYSIS.bounds_wgs84} layers={LAYERS} visible={{ ...ALL, roads: false, villages: false }} />);
    expect(screen.queryByTestId("pane-roads")).toBeNull();
    expect(screen.queryByTestId("pane-villages")).toBeNull();
    expect(screen.getByTestId("pane-zones")).toBeInTheDocument();
  });

  it("explains when the image has no usable position instead of drawing a map", () => {
    render(<AnalysisMap bounds={[1, 2]} layers={LAYERS} visible={ALL} />);
    expect(screen.getByText(/no usable map position/i)).toBeInTheDocument();
    expect(screen.queryByTestId("map")).toBeNull();
  });
});