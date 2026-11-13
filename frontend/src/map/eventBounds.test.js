import { describe, expect, it } from "vitest";
import { DEFAULT_BOUNDS, eventBounds } from "./eventBounds.js";

const analysis = (bbox) => ({ bounds_wgs84: bbox });
const pin = (lon, lat) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: {} });
const pins = (...features) => ({ type: "FeatureCollection", features });

describe("eventBounds", () => {
  it("falls back to the Assam region when there is nothing to show", () => {
    for (const [a, p] of [[[], null], [null, null], [undefined, pins()], [[], pins()]]) {
      expect(eventBounds(a, p)).toEqual(DEFAULT_BOUNDS);
    }
  });

  it("fits a single analysis exactly (latitude first)", () => {
    expect(eventBounds([analysis([93.7, 26.5, 93.75, 26.55])], null)).toEqual([
      [26.5, 93.7],
      [26.55, 93.75],
    ]);
  });

  it("covers several analyses", () => {
    const result = eventBounds([analysis([92.9, 26.58, 92.95, 26.63]), analysis([93.7, 26.53, 93.78, 26.58])], null);
    expect(result).toEqual([
      [26.53, 92.9],
      [26.63, 93.78],
    ]);
  });

  it("stretches to include a pin outside the analyses", () => {
    const result = eventBounds([analysis([93.7, 26.5, 93.75, 26.55])], pins(pin(94.2, 26.9)));
    expect(result).toEqual([
      [26.5, 93.7],
      [26.9, 94.2],
    ]);
  });

  it("widens the view around a single pin so the map is not zoomed in fully", () => {
    const [[south, west], [north, east]] = eventBounds([], pins(pin(93.7554, 26.5834)));
    expect(west).toBeCloseTo(93.7354, 6);
    expect(east).toBeCloseTo(93.7754, 6);
    expect(south).toBeCloseTo(26.5634, 6);
    expect(north).toBeCloseTo(26.6034, 6);
  });

  it("widens a very small box made of two close pins, but not a large one", () => {
    const [[south, west], [north, east]] = eventBounds([], pins(pin(93.7, 26.5), pin(93.701, 26.501)));
    expect(east - west).toBeGreaterThan(0.03);
    expect(north - south).toBeGreaterThan(0.03);
    const wide = eventBounds([], pins(pin(93.0, 26.0), pin(94.0, 27.0)));
    expect(wide).toEqual([
      [26.0, 93.0],
      [27.0, 94.0],
    ]);
  });

  it("ignores analyses with unusable bounds and pins with broken coordinates", () => {
    const result = eventBounds(
      [analysis([1, 2]), analysis(null), analysis([93.7, 26.5, 93.75, 26.55])],
      pins(pin(null, 26), { type: "Feature", geometry: null }, pin(500, 10), pin(93.72, 26.52)),
    );
    expect(result).toEqual([
      [26.5, 93.7],
      [26.55, 93.75],
    ]);
    expect(eventBounds([analysis([5, 5, 4, 4])], pins(pin(NaN, 1)))).toEqual(DEFAULT_BOUNDS);
  });
});
