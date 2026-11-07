import { describe, expect, it } from "vitest";
import { formatKm2, formatLength, formatMeters, formatPercent } from "./format.js";

describe("map format helpers", () => {
  it("formats areas with a chosen number of decimals", () => {
    expect(formatKm2(0.13246, 4)).toBe("0.1325");
    expect(formatKm2(0.13246)).toBe("0.13");
    expect(formatKm2(null, 4)).toBe("–");
  });

  it("shows short lengths in metres and long ones in kilometres", () => {
    expect(formatLength(0.058488)).toBe("58 m");
    expect(formatLength(0.9996)).toBe("1.00 km");
    expect(formatLength(1.662)).toBe("1.66 km");
    expect(formatLength(0)).toBe("0 m");
    expect(formatLength(undefined)).toBe("–");
  });

  it("formats distances and percentages", () => {
    expect(formatMeters(410.2)).toBe("410 m");
    expect(formatMeters(null)).toBe("–");
    expect(formatPercent(53.632)).toBe("53.6%");
    expect(formatPercent(null)).toBe("–");
  });
});
