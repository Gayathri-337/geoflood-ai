/** Checks the page makes before uploading. The server repeats and extends them. */

// Keep equal to the backend setting max_upload_mb (200 by default).
export const MAX_UPLOAD_MB = 200;

function checkTiff(file, label) {
  if (!/\.tiff?$/i.test(file.name)) return `The ${label} must be a GeoTIFF (.tif or .tiff).`;
  if (file.size === 0) return `The ${label} file is empty.`;
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `The ${label} is larger than the ${MAX_UPLOAD_MB} MB limit.`;
  return "";
}

/** An error message for the image, or "" if it looks fine. */
export function checkImageFile(file) {
  if (!file) return "Choose the Sentinel-1 image (a .tif or .tiff file).";
  return checkTiff(file, "image");
}

/** The baseline is optional: no file is fine. */
export function checkBaselineFile(file) {
  return file ? checkTiff(file, "baseline layer") : "";
}

/** "India_828067" from "India_828067_S1Hand.tif" (the dataset's naming), or null for any other name. */
export function chipPrefix(name) {
  const match = /^([A-Za-z][A-Za-z-]*_\d+)_/.exec(name || "");
  return match ? match[1] : null;
}

/** True only when both names follow the dataset pattern and name different chips. */
export function chipMismatch(imageName, baselineName) {
  const image = chipPrefix(imageName);
  const baseline = chipPrefix(baselineName);
  return image !== null && baseline !== null && image !== baseline;
}

// ---- Phase 29b: the date the satellite took the image (optional)
export const EARLIEST_DATE = "2000-01-01";

/** Today as YYYY-MM-DD in the browser's own time zone. */
export function todayString(now = new Date()) {
  const two = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())}`;
}

/** "" when the value is fine (or empty), otherwise a message. */
export function checkAcquiredDate(value, now = new Date()) {
  if (!value) return "";
  const parsed = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00Z`) : null;
  if (!parsed || Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) {
    return "The date the satellite took the image is not a real date.";
  }
  if (value < EARLIEST_DATE) return "The date the satellite took the image cannot be before the year 2000.";
  if (value > todayString(now)) return "The date the satellite took the image cannot be in the future.";
  return "";
}
