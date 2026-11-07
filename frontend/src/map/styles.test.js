import { describe, expect, it } from "vitest";
import { COLORS, LAYER_KEYS, PANE_Z } from "./layers.js";
import { areaStyle, pointToLayerFor, roadStyle, zoneStyle } from "./styles.js";

describe("map styles", () => {
  it("colours zones by type and falls back for anything else", () => {
    expect(zoneStyle({ properties: { zone_type: "new_flood" } }).fillColor).toBe(COLORS.newFlood);
    expect(zoneStyle({ properties: { zone_type: "permanent_water" } }).fillColor).toBe(COLORS.permanentWater);
    expect(zoneStyle({ properties: { zone_type: "water" } }).fillColor).toBe(COLORS.water);
    expect(zoneStyle({}).fillColor).toBe(COLORS.water);
    expect(zoneStyle(undefined).fillColor).toBe(COLORS.water);
    expect(COLORS.newFlood).not.toBe(COLORS.permanentWater);
  });

  it("draws roads thick and red", () => {
    expect(roadStyle()).toMatchObject({ color: COLORS.roads, weight: 5 });
  });

  it("fills areas with the layer's colour", () => {
    expect(areaStyle("farmland")).toMatchObject({ color: COLORS.farmland, fillColor: COLORS.farmland });
  });

  it("draws points as circles: big and solid inside the flooded area, small and faded when near it", () => {
    const toLayer = pointToLayerFor("villages");
    const inside = toLayer({ properties: { relation: "inside" } }, [26.5, 93.7]);
    const near = toLayer({ properties: { relation: "near" } }, [26.5, 93.7]);
    expect(inside.options.pane).toBe("villages");
    expect(inside.options.fillColor).toBe(COLORS.villages);
    expect(inside.options.radius).toBeGreaterThan(near.options.radius);
    expect(inside.options.fillOpacity).toBeGreaterThan(near.options.fillOpacity);
    expect(inside.getLatLng().lat).toBe(26.5);
    expect(inside.getLatLng().lng).toBe(93.7);
  });

  it("stacks the layers from the bottom: farmland, zones, roads, villages, facilities", () => {
    const order = ["farmland", "zones", "roads", "villages", "infrastructure"];
    const heights = order.map((key) => PANE_Z[key]);
    expect(heights).toEqual([...heights].sort((a, b) => a - b));
    expect(new Set(heights).size).toBe(5);
    expect([...LAYER_KEYS].sort()).toEqual([...order].sort());
  });
});
