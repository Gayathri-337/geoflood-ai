import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PINS } from "../eventFixtures.js";
import EventMap from "./EventMap.jsx";

const captured = vi.hoisted(() => ({ handlers: null, container: null }));

// The map library is replaced by simple elements, so these tests check WHAT is drawn, not how it looks.
vi.mock("react-leaflet", async () => {
  const React = await import("react");
  const h = React.createElement;
  return {
    MapContainer: ({ children, bounds }) => h("div", { "data-testid": "map", "data-bounds": JSON.stringify(bounds) }, children),
    TileLayer: ({ attribution, url }) => h("div", { "data-testid": "tiles", "data-attribution": attribution, "data-url": url }),
    GeoJSON: ({ data }) => h("div", { "data-testid": "pins", "data-count": String(data.features.length) }),
    CircleMarker: ({ center }) => h("div", { "data-testid": "picked", "data-center": JSON.stringify(center) }),
    useMap: () => ({ getContainer: () => captured.container }),
    useMapEvents: (handlers) => {
      captured.handlers = handlers;
      return null;
    },
  };
});

const BOUNDS = [[26.0, 92.8], [26.7, 93.8]];
const click = (lat, lng) => captured.handlers.click({ latlng: { lat, lng } });

beforeEach(() => {
  captured.handlers = null;
  captured.container = document.createElement("div");
});

describe("EventMap", () => {
  it("uses OpenStreetMap tiles and shows the attribution", () => {
    render(<EventMap bounds={BOUNDS} pins={PINS} />);
    const tiles = screen.getByTestId("tiles");
    expect(tiles.dataset.url).toBe("https://tile.openstreetmap.org/{z}/{x}/{y}.png");
    expect(tiles.dataset.attribution).toContain("OpenStreetMap");
    expect(tiles.dataset.attribution).toContain("openstreetmap.org/copyright");
  });

  it("fits the map to the bounds it is given", () => {
    render(<EventMap bounds={BOUNDS} pins={PINS} />);
    expect(JSON.parse(screen.getByTestId("map").dataset.bounds)).toEqual(BOUNDS);
  });

  it("draws the pins, and nothing when there are none", () => {
    const { rerender } = render(<EventMap bounds={BOUNDS} pins={PINS} />);
    expect(screen.getByTestId("pins").dataset.count).toBe("2");
    rerender(<EventMap bounds={BOUNDS} pins={{ type: "FeatureCollection", features: [] }} />);
    expect(screen.queryByTestId("pins")).toBeNull();
    rerender(<EventMap bounds={BOUNDS} pins={null} />);
    expect(screen.queryByTestId("pins")).toBeNull();
  });

  it("reports a click as (longitude, latitude) only while picking", () => {
    const onPick = vi.fn();
    const { rerender } = render(<EventMap bounds={BOUNDS} pins={PINS} picking={false} onPick={onPick} />);
    click(26.5834, 93.7554);
    expect(onPick).not.toHaveBeenCalled();

    rerender(<EventMap bounds={BOUNDS} pins={PINS} picking onPick={onPick} />);
    click(26.5834, 93.7554);
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick).toHaveBeenCalledWith(93.7554, 26.5834);
  });

  it("marks the position that was picked, latitude first", () => {
    const { rerender } = render(<EventMap bounds={BOUNDS} pins={PINS} picked={null} />);
    expect(screen.queryByTestId("picked")).toBeNull();
    rerender(<EventMap bounds={BOUNDS} pins={PINS} picked={{ longitude: 93.7554, latitude: 26.5834 }} />);
    expect(JSON.parse(screen.getByTestId("picked").dataset.center)).toEqual([26.5834, 93.7554]);
  });

  it("shows a crosshair cursor while picking and restores it afterwards", () => {
    const { rerender, unmount } = render(<EventMap bounds={BOUNDS} pins={PINS} picking />);
    expect(captured.container.style.cursor).toBe("crosshair");
    rerender(<EventMap bounds={BOUNDS} pins={PINS} picking={false} />);
    expect(captured.container.style.cursor).toBe("");
    unmount();
  });
});
