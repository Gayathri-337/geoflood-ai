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
