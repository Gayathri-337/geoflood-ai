"""GeoFlood AI backend - upload an image and detect water."""

import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from rasterio.transform import array_bounds
from rasterio.warp import transform_bounds

from backend.config import Settings, get_settings
from backend.schemas.prediction import PredictionOut
from backend.services.inference import ModelService, ModelUnavailable, get_model_service
from backend.services.uploads import (UploadRejected, check_suffix, clean_filename,
                                      inspect_geotiff, save_upload)
from gis.area_calculator import analyze_water

router = APIRouter(prefix="/predict", tags=["prediction"])

RUN_ID_PATTERN = r"^[0-9a-f]{32}$"
MASK_FILE = "input_floodmask.tif"     # written by ai.src.predict from the stored file input.tif


@router.post("", response_model=PredictionOut, status_code=201)
def predict_upload(
    file: UploadFile = File(..., description="2-band Sentinel-1 GeoTIFF (VV, VH) in dB"),
    settings: Settings = Depends(get_settings),
    models: ModelService = Depends(get_model_service),
):
    """
    Upload a Sentinel-1 GeoTIFF and detect surface water.

    The model detects ALL surface water, rivers included. It does not tell new flooding from
    permanent water; that needs a baseline (added in Phase 17).
    """
    if not models.loaded:
        raise HTTPException(503, "The flood model is not loaded, so predictions are unavailable.")

    started = time.perf_counter()
    name = clean_filename(file.filename)
    check_suffix(name)

    run_id = uuid.uuid4().hex
    in_dir = settings.uploads_dir / run_id
    out_dir = settings.outputs_dir / run_id
    try:
        in_dir.mkdir(parents=True)
        out_dir.mkdir(parents=True)
        input_path = in_dir / "input.tif"

        save_upload(file.file, input_path, settings.max_upload_mb)
        inspect_geotiff(input_path, models.in_channels, settings.max_pixels)

        try:
            result = models.predict(input_path, out_dir)
            areas = analyze_water(result.mask, result.transform, result.crs)
        except ModelUnavailable:
            raise HTTPException(503, "The flood model is not loaded, so predictions are unavailable.")
        except ValueError as err:
            raise UploadRejected(422, str(err))

        stats = result.stats
        west, south, east, north = transform_bounds(
            result.crs, "EPSG:4326",
            *array_bounds(stats["height"], stats["width"], result.transform))

        out = PredictionOut(
            run_id=run_id,
            original_filename=name,
            created_at=datetime.now(timezone.utc),
            processing_seconds=round(time.perf_counter() - started, 2),
            model_checkpoint=stats["model_checkpoint"],
            threshold=stats["threshold"],
            height_px=stats["height"],
            width_px=stats["width"],
            crs=result.crs.to_string(),
            bounds_wgs84=[round(v, 6) for v in (west, south, east, north)],
            valid_pixels=stats["valid_pixels"],
            water_pixels=stats["flood_pixels"],
            mean_water_confidence=stats["mean_flood_confidence"],
            valid_area_km2=areas["valid_area_km2"],
            nodata_area_km2=areas["nodata_area_km2"],
            water_area_km2=areas["water_area_km2"],
            water_pct_of_valid=areas["water_pct_of_valid"],
            area_method=areas["area_method"],
            warnings=stats["warnings"],
            mask_url=f"/api/predict/{run_id}/mask",
        )
        (out_dir / "result.json").write_text(out.model_dump_json(indent=2))
        return out
    except Exception:
        # a failed run must leave nothing behind
        shutil.rmtree(in_dir, ignore_errors=True)
        shutil.rmtree(out_dir, ignore_errors=True)
        raise


@router.get("/{run_id}", response_model=PredictionOut)
def get_prediction(run_id: str = PathParam(pattern=RUN_ID_PATTERN),
                   settings: Settings = Depends(get_settings)):
    """The stored result of an earlier run."""
    path = settings.outputs_dir / run_id / "result.json"
    if not path.is_file():
        raise HTTPException(404, f"Run {run_id} not found")
    return PredictionOut.model_validate_json(path.read_text())


@router.get("/{run_id}/mask")
def download_mask(run_id: str = PathParam(pattern=RUN_ID_PATTERN),
                  settings: Settings = Depends(get_settings)):
    """The water mask of a run as a georeferenced GeoTIFF (0 = not water, 1 = water, 255 = no data)."""
    path: Path = settings.outputs_dir / run_id / MASK_FILE
    if not path.is_file():
        raise HTTPException(404, f"Run {run_id} not found")
    return FileResponse(path, media_type="image/tiff", filename=f"{run_id}_water_mask.tif")
