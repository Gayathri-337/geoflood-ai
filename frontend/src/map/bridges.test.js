import { describe, expect, it } from "vitest";
import { COLORS } from "./layers.js";
import { popupFor } from "./popups.js";
import { roadStyle } from "./styles.js";

describe("bridges on the map", () => {
  it("draws a bridge dashed and grey, and a flooded road solid and red", () => {
    const bridge = roadStyle({ properties: { on_bridge: true } });
    const road = roadStyle({ properties: { on_bridge: false } });
    expect(bridge.color).toBe(COLORS.bridges);
    expect(bridge.dashArray).toBeTruthy();
    expect(road.color).toBe(COLORS.roads);
    expect(road.dashArray).toBeUndefined();
    expect(COLORS.bridges).not.toBe(COLORS.roads);
  });

  it("says in the popup that a bridge is not counted as flooded", () => {
    const text = popupFor("roads", {
      name: null, category: "trunk", source_ref: "way/1", flooded_length_km: 0.058488, flooded_pct: 53.632, on_bridge: true,
    }).textContent;
    expect(text).toContain("Bridge:");
    expect(text).toContain("not counted as a flooded road");
    expect(text).toContain("Length over the water: 58 m");
    expect(text).not.toContain("Flooded length");
  });

  it("keeps the flooded-road wording for a road that is not a bridge", () => {
    const text = popupFor("roads", { name: "Test Road", category: "residential", flooded_length_km: 0.12, flooded_pct: 80, on_bridge: false }).textContent;
    expect(text).toContain("Flooded length: 120 m");
    expect(text).not.toContain("Bridge:");
  });
});

