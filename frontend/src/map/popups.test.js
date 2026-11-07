import { describe, expect, it } from "vitest";
import { buildPopup, popupFor } from "./popups.js";

describe("popups", () => {
  it("shows OpenStreetMap text as text, never as markup", () => {
    const evil = '<img src=x onerror="alert(1)">';
    const popup = popupFor("villages", { name: evil, category: "village", relation: "inside", distance_m: 0 });
    expect(popup.querySelector("img")).toBeNull();
    expect(popup.textContent).toContain(evil);
    const plain = buildPopup("<b>title</b>", [["label", "<i>value</i>"]]);
    expect(plain.querySelector("b")).toBeNull();
    expect(plain.querySelector("i")).toBeNull();
  });

  it("describes a road: name fallback, class, flooded length in metres, share, OSM id", () => {
    const text = popupFor("roads", {
      name: null, category: "trunk", source_ref: "way/224005043", flooded_length_km: 0.058488, flooded_pct: 53.632,
    }).textContent;
    for (const part of ["Unnamed road", "Road class: trunk", "Flooded length: 58 m", "53.6%", "way/224005043"]) {
      expect(text).toContain(part);
    }
  });

  it("describes farmland with its flooded area and share", () => {
    const text = popupFor("farmland", {
      name: "Field F", category: "farmland", flooded_area_km2: 0.1324, flooded_pct: 37.5, source_ref: "way/20",
    }).textContent;
    for (const part of ["Field F", "0.1324 km²", "37.5%", "way/20"]) expect(text).toContain(part);
  });

  it("tells inside from near for villages and says how far", () => {
    const inside = popupFor("villages", { name: "A", category: "village", relation: "inside", distance_m: 0 }).textContent;
    const near = popupFor("villages", { name: "B", category: "hamlet", relation: "near", distance_m: 410.2 }).textContent;
    expect(inside).toContain("Inside the flooded area");
    expect(near).toContain("Near: 410 m from the flooded area");
    expect(popupFor("villages", { category: "village" }).textContent).toContain("Unnamed place");
  });

  it("describes a facility", () => {
    const text = popupFor("infrastructure", {
      name: "Test College", category: "college", relation: "near", distance_m: 260, source_ref: "node/20",
    }).textContent;
    for (const part of ["Test College", "Type: college", "Near: 260 m", "node/20"]) expect(text).toContain(part);
  });

  it("titles water zones by type and survives missing numbers", () => {
    expect(popupFor("zones", { zone_type: "new_flood", area_km2: 0.2, n_pixels: 500, mean_confidence: 0.95 }).textContent).toContain(
      "New water vs baseline",
    );
    expect(popupFor("zones", { zone_type: "permanent_water" }).textContent).toContain("Permanent water");
    const empty = popupFor("zones", { zone_type: "water" }).textContent;
    expect(empty).toContain("Detected water");
    expect(empty).toContain("Average model confidence: –");
  });

  it("does not crash for an unknown layer or missing properties", () => {
    expect(popupFor("nonsense", {}).textContent).toBe("Feature");
    expect(popupFor("roads", null).textContent).toContain("Unnamed road");
  });
});
