import { describe, expect, it } from "vitest";
import { formatDate, formatInt, formatKm2 } from "./format.js";

describe("format helpers", () => {
  it("formats areas with two decimals and shows a dash for missing values", () => {
    expect(formatKm2(10.74337)).toBe("10.74");
    expect(formatKm2(0)).toBe("0.00");
    expect(formatKm2(null)).toBe("–");
    expect(formatKm2(undefined)).toBe("–");
  });

  it("formats whole numbers", () => {
    expect(formatInt(99)).toBe("99");
    expect(formatInt(1234567)).toBe("12,34,567");
    expect(formatInt(null)).toBe("–");
  });

  it("formats dates and survives bad input", () => {
    expect(formatDate("2026-11-03T17:06:12Z")).not.toBe("–");
    expect(formatDate(null)).toBe("–");
    expect(formatDate("not a date")).toBe("–");
  });
});
