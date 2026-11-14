import { describe, expect, it } from "vitest";
import { chartModel, directionText, formatDays, formatDelta, formatObserved, formatPctChange } from "./progression.js";
import { PROGRESSION } from "./progressionFixtures.js";

describe("progression formatting", () => {
  it("shows a midnight value as a date and other times with the time", () => {
    expect(formatObserved("2026-10-27T00:00:00Z")).toBe("2026-10-27");
    expect(formatObserved("2026-10-27T05:30:00Z")).toBe("2026-10-27 05:30 UTC");
    expect(formatObserved(null)).toBe("–");
    expect(formatObserved("nonsense")).toBe("–");
  });

  it("shows a sign on changes and never a minus on zero", () => {
    expect(formatDelta(1.7)).toBe("+1.70 km²");
    expect(formatDelta(-0.4)).toBe("−0.40 km²");
    expect(formatDelta(0)).toBe("0.00 km²");
    expect(formatDelta(-0.001)).toBe("0.00 km²");
    expect(formatDelta(null)).toBe("–");
    expect(formatPctChange(68)).toBe("+68.0%");
    expect(formatPctChange(-50)).toBe("−50.0%");
    expect(formatPctChange(null)).toBe("–");
  });

  it("words the number of days", () => {
    expect(formatDays(1)).toBe("1 day");
    expect(formatDays(6)).toBe("6 days");
    expect(formatDays(2.5)).toBe("2.5 days");
    expect(formatDays(null)).toBe("–");
  });

  it("describes a direction in terms of detected water, never as confirmed flooding", () => {
    expect(directionText("more")).toBe("More detected water");
    expect(directionText("less")).toBe("Less detected water");
    expect(directionText("similar")).toBe("About the same");
    expect(directionText(null)).toBe("Not available");
    for (const d of ["more", "less", "similar", null]) expect(directionText(d)).not.toMatch(/flood/i);
  });
});

describe("chartModel", () => {
  const series = PROGRESSION.series[0];

  it("places the points by date, with larger areas higher up", () => {
    const m = chartModel(series);
    expect(m.points).toHaveLength(3);
    const [a, b, c] = m.points;
    expect(a.x).toBeLessThan(b.x);
    expect(b.x).toBeLessThan(c.x);
    expect(c.y).toBeLessThan(b.y); // smaller y = higher on screen
    expect(b.y).toBeLessThan(a.y);
    expect(m.path.startsWith("M")).toBe(true);
    expect(m.path.match(/L/g)).toHaveLength(2);
  });

  it("spaces the points by the real dates, not evenly", () => {
    const uneven = {
      points: [
        { analysis_id: 1, observed_at: "2026-10-01T00:00:00Z", water_area_km2: 1 },
        { analysis_id: 2, observed_at: "2026-10-02T00:00:00Z", water_area_km2: 2 },
        { analysis_id: 3, observed_at: "2026-10-11T00:00:00Z", water_area_km2: 3 },
      ],
    };
    const [a, b, c] = chartModel(uneven).points;
    expect((b.x - a.x) / (c.x - a.x)).toBeCloseTo(0.1, 5);
  });

  it("starts the vertical axis at 0 km² and keeps every point inside the drawing", () => {
    const m = chartModel(series);
    expect(m.yTicks.map((tick) => tick.label)).toEqual(["0", "4", "8"]);
    expect(m.baselineY).toBeGreaterThan(Math.max(...m.points.map((p) => p.y)));
    for (const p of m.points) {
      expect(p.x).toBeGreaterThanOrEqual(m.margin.left);
      expect(p.x).toBeLessThanOrEqual(m.right);
      expect(p.y).toBeGreaterThanOrEqual(m.margin.top);
    }
  });

  it("leaves out dates without a water area, and gives up when fewer than two remain", () => {
    const holes = {
      points: [
        { analysis_id: 1, observed_at: "2026-10-01T00:00:00Z", water_area_km2: null },
        { analysis_id: 2, observed_at: "2026-10-02T00:00:00Z", water_area_km2: 2 },
        { analysis_id: 3, observed_at: "2026-10-03T00:00:00Z", water_area_km2: 3 },
      ],
    };
    expect(chartModel(holes).points.map((p) => p.analysis_id)).toEqual([2, 3]);
    expect(chartModel({ points: holes.points.slice(0, 2) })).toBeNull();
    expect(chartModel({ points: [] })).toBeNull();
    expect(chartModel(null)).toBeNull();
  });

  it("copes with a series where every area is 0", () => {
    const zeros = {
      points: [
        { analysis_id: 1, observed_at: "2026-10-01T00:00:00Z", water_area_km2: 0 },
        { analysis_id: 2, observed_at: "2026-10-05T00:00:00Z", water_area_km2: 0 },
      ],
    };
    const m = chartModel(zeros);
    expect(m.points.every((p) => Number.isFinite(p.y))).toBe(true);
  });
});
