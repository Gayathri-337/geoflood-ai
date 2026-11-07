import { describe, expect, it } from "vitest";
import { toLeafletBounds } from "./bounds.js";

describe("toLeafletBounds", () => {
  it("turns [west, south, east, north] into Leaflet's [[south, west], [north, east]]", () => {
    expect(toLeafletBounds([92.9, 26.58, 92.95, 26.63])).toEqual([
      [26.58, 92.9],
      [26.63, 92.95],
    ]);
  });

  it("rejects anything that is not four finite numbers", () => {
    for (const bad of [undefined, null, [], [1, 2, 3], "92.9,26.5,92.95,26.6", ["a", 2, 3, 4], [NaN, 1, 2, 3], [1, 2, Infinity, 4]]) {
      expect(toLeafletBounds(bad)).toBeNull();
    }
  });

  it("rejects reversed or out-of-range boxes", () => {
    expect(toLeafletBounds([93, 26, 92, 27])).toBeNull();
    expect(toLeafletBounds([92, 27, 93, 26])).toBeNull();
    expect(toLeafletBounds([-181, 0, 10, 10])).toBeNull();
    expect(toLeafletBounds([0, -91, 10, 10])).toBeNull();
  });
});
