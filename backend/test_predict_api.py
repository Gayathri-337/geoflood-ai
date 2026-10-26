"""
GeoFlood AI - Phase 16 test: upload -> U-Net -> result, through the real API code.

The expected numbers for India_591317 are the ones measured earlier:
  Phase 9 (predict.py):       120653 water pixels, mean confidence 0.9686, 262144 valid pixels
  Phase 12 (area_calculator): valid 23.343952 km2, water 10.74337 km2, 46.022 % of the valid area

Usage (project root):  python -m backend.test_predict_api
"""

import hashlib
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from ai.src import config
from backend.config import Settings, get_settings
from backend.main import app
from backend.services.inference import ModelService

SEP = "=" * 70
CHIP = config.IMG_DIR / "India_591317_S1Hand.tif"


def ok(message):
    print(f"  [OK] {message}")


def make_settings(tmp, **extra):
    return Settings(uploads_dir=tmp / "uploads", outputs_dir=tmp / "outputs", **extra)


def use(settings):
    app.dependency_overrides[get_settings] = lambda: settings


def snapshot(tmp):
    """Names of the run folders that currently exist."""
    return tuple(sorted(p.name for p in (tmp / d).glob("*")) for d in ("uploads", "outputs"))


def post(client, name, data):
    return client.post("/api/predict", files={"file": (name, data, "application/octet-stream")})


def write_tif(path, array, crs="EPSG:4326"):
    with rasterio.open(path, "w", driver="GTiff", height=array.shape[1], width=array.shape[2],
                       count=array.shape[0], dtype="float32", crs=crs,
                       transform=from_origin(92.9, 26.6, 0.0001, 0.0001)) as dst:
        dst.write(array.astype("float32"))
    return path.read_bytes()


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 16 Prediction API Test")
    print(SEP)
    if not CHIP.exists():
        raise SystemExit(f"Test chip not found: {CHIP}")
    chip_bytes = CHIP.read_bytes()

    with tempfile.TemporaryDirectory() as tmp_name, TestClient(app) as client:   # "with" runs the model load
        tmp = Path(tmp_name)
        base = make_settings(tmp)
        use(base)

        # ------------------------------------------------------------ 1
        print("\n--- 1. The model is loaded at server start ---")
        r = client.get("/api/health/model")
        j = r.json()
        assert r.status_code == 200 and j["status"] == "ok" and j["loaded"] is True, r.text
        ok(f"GET /api/health/model -> {j['checkpoint']} on {j['device']}, threshold {j['threshold']}")

        # ------------------------------------------------------------ 2
        print("\n--- 2. Upload a real chip (India_591317) ---")
        r = post(client, CHIP.name, chip_bytes)
        assert r.status_code == 201, r.text
        res = r.json()
        run_id = res["run_id"]
        assert len(run_id) == 32 and res["original_filename"] == CHIP.name
        assert res["valid_pixels"] == 262144 and res["warnings"] == []
        assert abs(res["water_pixels"] - 120653) <= 240, res["water_pixels"]
        assert abs(res["valid_area_km2"] - 23.343952) < 0.001, res["valid_area_km2"]
        assert abs(res["water_area_km2"] - 10.74337) / 10.74337 < 0.005, res["water_area_km2"]
        assert abs(res["water_pct_of_valid"] - 46.022) < 0.05, res["water_pct_of_valid"]
        assert abs(res["mean_water_confidence"] - 0.9686) < 0.002
        assert res["crs"] == "EPSG:4326" and "surface water" in res["detects"]
        with rasterio.open(CHIP) as src:
            expected_bounds = [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]
        assert all(abs(a - b) < 1e-5 for a, b in zip(res["bounds_wgs84"], expected_bounds))
        ok(f"201 Created, run {run_id[:8]}..., processed in {res['processing_seconds']} s")
        ok(f"water pixels {res['water_pixels']:,} (Phase 9: 120,653); "
           f"area {res['water_area_km2']:.4f} km2 (Phase 12: 10.7434)")
        ok(f"{res['water_pct_of_valid']}% of the valid area, mean confidence "
           f"{res['mean_water_confidence']} (Phase 9: 0.9686), bounds match the file")

        # ------------------------------------------------------------ 3
        print("\n--- 3. What was saved ---")
        stored = tmp / "uploads" / run_id / "input.tif"
        assert hashlib.sha256(stored.read_bytes()).hexdigest() == hashlib.sha256(chip_bytes).hexdigest()
        outs = sorted(p.name for p in (tmp / "outputs" / run_id).iterdir())
        assert outs == ["input_floodmask.tif", "input_floodprob.tif", "result.json"], outs
        ok("the stored upload is byte-for-byte identical to what was sent")
        ok(f"outputs: {', '.join(outs)}")

        # ------------------------------------------------------------ 4
        print("\n--- 4. Reading the result back and downloading the mask ---")
        r = client.get(f"/api/predict/{run_id}")
        assert r.status_code == 200 and r.json() == res
        ok("GET /api/predict/{run_id} returns exactly what the upload returned")
        r = client.get(res["mask_url"])
        assert r.status_code == 200 and r.headers["content-type"] == "image/tiff"
        mask_file = tmp / "downloaded_mask.tif"
        mask_file.write_bytes(r.content)
        with rasterio.open(CHIP) as a, rasterio.open(mask_file) as b:
            assert b.crs == a.crs and b.transform == a.transform
            assert (b.height, b.width) == (a.height, a.width)
            assert b.dtypes[0] == "uint8" and b.nodata == 255
            assert int((b.read(1) == 1).sum()) == res["water_pixels"]
        ok("downloaded mask: same CRS, transform and size as the input; nodata 255; "
           "its water pixels equal the reported count")

        # ------------------------------------------------------------ 5
        print("\n--- 5. Run ids are checked ---")
        assert client.get("/api/predict/not-a-valid-id").status_code == 422
        assert client.get("/api/predict/" + run_id.upper()).status_code == 422
        assert client.get("/api/predict/" + "0" * 32).status_code == 404
        assert client.get("/api/predict/" + "0" * 32 + "/mask").status_code == 404
        ok("malformed ids -> 422; an unknown but well-formed id -> 404")

        # ------------------------------------------------------------ 6
        print("\n--- 6. Bad uploads are refused and leave nothing behind ---")
        three = write_tif(tmp / "three.tif", np.random.randn(3, 64, 64))
        nocrs = write_tif(tmp / "nocrs.tif", np.random.randn(2, 64, 64), crs=None)
        cases = [
            ("a .txt file", base, "notes.txt", b"hello", 415, "GeoTIFF"),
            ("text pretending to be a .tif", base, "fake.tif", b"this is not an image", 422, "could not be read"),
            ("an empty file", base, "empty.tif", b"", 422, "empty"),
            ("a 3-band image", base, "three.tif", three, 422, "band"),
            ("an image with no coordinate system", base, "nocrs.tif", nocrs, 422, "coordinate system"),
            ("an image over the pixel limit", make_settings(tmp, max_pixels=1000), CHIP.name, chip_bytes, 413, "pixels"),
            ("a file over the size limit", make_settings(tmp, max_upload_mb=1), CHIP.name, chip_bytes, 413, "limit"),
        ]
        for label, settings_for_case, name, data, status, fragment in cases:
            use(settings_for_case)
            before = snapshot(tmp)
            r = post(client, name, data)
            assert r.status_code == status, f"{label}: expected {status}, got {r.status_code} {r.text}"
            assert fragment in r.json()["detail"], f"{label}: {r.json()}"
            assert snapshot(tmp) == before, f"{label}: files were left behind"
            ok(f"{label} -> {status}: {r.json()['detail']}")
        use(base)

        # ------------------------------------------------------------ 7
        print("\n--- 7. A hostile file name cannot escape the upload folder ---")
        r = post(client, "../../evil.tif", chip_bytes)
        assert r.status_code == 201, r.text
        name = r.json()["original_filename"]
        assert "/" not in name and ".." not in name
        run2 = r.json()["run_id"]
        assert (tmp / "uploads" / run2 / "input.tif").is_file()
        assert not (tmp.parent / "evil.tif").exists()
        ok(f"'../../evil.tif' was stored under the random run folder; the name became '{name}'")

        # ------------------------------------------------------------ 8
        print("\n--- 8. An image that does not look like dB values still runs, with a warning ---")
        odd = write_tif(tmp / "odd.tif", np.random.uniform(0, 255, (2, 70, 50)))
        r = post(client, "odd.tif", odd)
        assert r.status_code == 201, r.text
        j = r.json()
        assert (j["height_px"], j["width_px"]) == (70, 50) and j["warnings"]
        ok(f"70 x 50 image accepted; warning: {j['warnings'][0]}")

        # ------------------------------------------------------------ 9
        print("\n--- 9. When the model is not available ---")
        real_service = app.state.model_service
        broken = ModelService(tmp / "missing.pth")
        broken.load()
        app.state.model_service = broken
        before = snapshot(tmp)
        r = client.get("/api/health/model")
        assert r.status_code == 200 and r.json()["status"] == "unavailable" and r.json()["loaded"] is False
        ok(f"GET /api/health/model -> unavailable ({r.json()['detail']})")
        r = post(client, CHIP.name, chip_bytes)
        assert r.status_code == 503 and snapshot(tmp) == before
        ok("POST /api/predict -> 503 and nothing was saved")
        app.state.model_service = real_service
        r = post(client, CHIP.name, chip_bytes)
        assert r.status_code == 201
        ok("with the real model back, uploads work again")

    app.dependency_overrides.clear()
    print("\n" + SEP)
    print("  Prediction API tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
