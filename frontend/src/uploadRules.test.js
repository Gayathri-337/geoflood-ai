import { describe, expect, it } from "vitest";
import { MAX_UPLOAD_MB, checkBaselineFile, checkImageFile, chipMismatch, chipPrefix } from "./uploadRules.js";

const file = (name, size = 100) => {
  const f = new File(["x"], name);
  Object.defineProperty(f, "size", { value: size });
  return f;
};

describe("upload rules", () => {
  it("accepts a GeoTIFF and refuses a missing, mistyped, empty or oversized image", () => {
    expect(checkImageFile(file("a.tif"))).toBe("");
    expect(checkImageFile(file("A.TIFF"))).toBe("");
    expect(checkImageFile(null)).toMatch(/Choose the Sentinel-1 image/);
    expect(checkImageFile(file("notes.txt"))).toMatch(/must be a GeoTIFF/);
    expect(checkImageFile(file("photo.tif.png"))).toMatch(/must be a GeoTIFF/);
    expect(checkImageFile(file("a.tif", 0))).toMatch(/empty/);
    expect(checkImageFile(file("a.tif", MAX_UPLOAD_MB * 1024 * 1024 + 1))).toMatch(/larger than the 200 MB limit/);
    expect(checkImageFile(file("a.tif", MAX_UPLOAD_MB * 1024 * 1024))).toBe("");
  });

  it("treats the baseline as optional but applies the same file rules", () => {
    expect(checkBaselineFile(null)).toBe("");
    expect(checkBaselineFile(file("b.tif"))).toBe("");
    expect(checkBaselineFile(file("b.csv"))).toMatch(/baseline layer must be a GeoTIFF/);
  });

  it("reads the chip from the dataset's file names", () => {
    expect(chipPrefix("India_828067_S1Hand.tif")).toBe("India_828067");
    expect(chipPrefix("Sri-Lanka_1038087_JRCWaterHand.tif")).toBe("Sri-Lanka_1038087");
    expect(chipPrefix("scene.tif")).toBeNull();
    expect(chipPrefix("")).toBeNull();
    expect(chipPrefix(undefined)).toBeNull();
  });

  it("flags a mismatch only when both names follow the pattern and differ", () => {
    expect(chipMismatch("India_828067_S1Hand.tif", "India_591317_JRCWaterHand.tif")).toBe(true);
    expect(chipMismatch("India_828067_S1Hand.tif", "India_828067_JRCWaterHand.tif")).toBe(false);
    expect(chipMismatch("my_scene.tif", "India_828067_JRCWaterHand.tif")).toBe(false);
    expect(chipMismatch("India_828067_S1Hand.tif", "baseline.tif")).toBe(false);
  });
});
