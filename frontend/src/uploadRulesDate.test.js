import { describe, expect, it } from "vitest";
import { checkAcquiredDate, todayString } from "./uploadRules.js";

const NOW = new Date(2026, 10, 14, 20, 22); // 14 Nov 2026, local time

describe("the date the satellite took the image", () => {
  it("formats today in the local time zone", () => {
    expect(todayString(NOW)).toBe("2026-11-14");
    expect(todayString(new Date(2026, 0, 5))).toBe("2026-01-05");
  });

  it("accepts nothing, today and earlier dates", () => {
    expect(checkAcquiredDate("", NOW)).toBe("");
    expect(checkAcquiredDate(undefined, NOW)).toBe("");
    expect(checkAcquiredDate("2026-10-27", NOW)).toBe("");
    expect(checkAcquiredDate("2026-11-14", NOW)).toBe("");
    expect(checkAcquiredDate("2000-01-01", NOW)).toBe("");
  });

  it("refuses dates that do not exist, are written differently, are too old or are in the future", () => {
    expect(checkAcquiredDate("2026-02-30", NOW)).toMatch(/not a real date/);
    expect(checkAcquiredDate("27/10/2026", NOW)).toMatch(/not a real date/);
    expect(checkAcquiredDate("yesterday", NOW)).toMatch(/not a real date/);
    expect(checkAcquiredDate("1999-12-31", NOW)).toMatch(/before the year 2000/);
    expect(checkAcquiredDate("2026-11-15", NOW)).toMatch(/in the future/);
    expect(checkAcquiredDate("2999-01-01", NOW)).toMatch(/in the future/);
  });
});
