"""
GeoFlood AI backend - upload handling and validation.

UploadRejected carries the HTTP status and a message that is safe to show to the user.
"""

import re
from pathlib import Path

import rasterio
from rasterio.errors import RasterioError

ALLOWED_SUFFIXES = {".tif", ".tiff"}
CHUNK_BYTES = 1024 * 1024


class UploadRejected(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def clean_filename(name) -> str:
    """Keep only a safe file name: no folders, no unusual characters, at most 100 characters."""
    base = Path(name or "").name
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:100]
    return base or "upload.tif"


def check_suffix(name: str) -> None:
    if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise UploadRejected(415, "Only GeoTIFF files (.tif or .tiff) are accepted.")


def save_upload(upload_file, dest: Path, max_mb: int) -> int:
    """Copy the upload to disk in chunks, refusing it as soon as it exceeds max_mb."""
    max_bytes = max_mb * 1024 * 1024
    total = 0
    with open(dest, "wb") as out:
        while True:
            chunk = upload_file.read(CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise UploadRejected(413, f"The file is larger than the {max_mb} MB limit.")
            out.write(chunk)
    if total == 0:
        raise UploadRejected(422, "The uploaded file is empty.")
    return total


def inspect_geotiff(path: Path, expected_bands: int, max_pixels: int) -> dict:
    """Check that the file is a readable, georeferenced image of the right shape."""
    try:
        with rasterio.open(path) as src:
            info = {"bands": src.count, "width": src.width, "height": src.height, "crs": src.crs}
    except RasterioError:
        raise UploadRejected(422, "The file could not be read as a GeoTIFF image.")

    if info["bands"] != expected_bands:
        raise UploadRejected(422, f"The image has {info['bands']} band(s); the model needs "
                                  f"{expected_bands} (Sentinel-1 VV and VH in dB).")
    if info["crs"] is None:
        raise UploadRejected(422, "The image has no coordinate system, so it cannot be placed "
                                  "on a map or measured in km2.")
    pixels = info["width"] * info["height"]
    if pixels > max_pixels:
        raise UploadRejected(413, f"The image has {pixels:,} pixels; the limit is {max_pixels:,}.")
    return info
