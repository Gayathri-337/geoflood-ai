"""GeoFlood AI backend - analyses: run the model, store the results, serve the GIS data."""

import json
import shutil
import time
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database import get_db
from backend.schemas.analysis import AnalysisOut
from backend.services import analysis_service as svc
from backend.services.inference import ModelService, ModelUnavailable, get_model_service
from backend.services.uploads import (UploadRejected, check_suffix, clean_filename,
                                      inspect_geotiff, save_upload)
from gis.area_calculator import analyze_water

router = APIRouter(prefix="/analyses", tags=["analyses"])

MAX_BIGINT = 2 ** 63 - 1
ZoneType = Literal["water", "permanent_water", "new_flood"]


def _exists(db: Session, table: str, column: str, value: int) -> bool:
    # table and column names are fixed strings written below, never user input
    return db.execute(text(f"SELECT 1 FROM {table} WHERE {column} = :v"), {"v": value}).first() is not None


@router.post("", response_model=AnalysisOut, status_code=201)
def create_analysis(
    file: UploadFile = File(..., description="2-band Sentinel-1 GeoTIFF (VV, VH) in dB"),
    event_id: int = Form(..., ge=1, le=MAX_BIGINT),
    source_id: int = Form(..., ge=1, le=MAX_BIGINT),
    baseline_file: Optional[UploadFile] = File(
        None, description="Optional 1-band GeoTIFF on the same grid as the image, 1 = water "
                          "(for example the JRCWaterHand file of a dataset chip)"),
    settings: Settings = Depends(get_settings),
    models: ModelService = Depends(get_model_service),
    db: Session = Depends(get_db),
):
    """
    Run the U-Net on an uploaded image and store the analysis for an event.

    Without a baseline layer the result is total surface water. With one, the water is split
    into permanent water (on the baseline) and new flood (not on the baseline). 'New flood' is
    an approximation: it also contains seasonal water and anything the baseline missed.
    """
    if not models.loaded:
        raise HTTPException(503, "The flood model is not loaded, so analyses are unavailable.")
    if not _exists(db, "disaster_events", "event_id", event_id):
        raise HTTPException(404, f"Event {event_id} not found")
    if not _exists(db, "satellite_sources", "source_id", source_id):
        raise HTTPException(404, f"Satellite source {source_id} not found")

    name = clean_filename(file.filename)
    check_suffix(name)
    if baseline_file is not None:
        check_suffix(clean_filename(baseline_file.filename))

    run_id = uuid.uuid4().hex
    in_dir = settings.uploads_dir / run_id
    out_dir = settings.outputs_dir / run_id
    try:
        in_dir.mkdir(parents=True)
        out_dir.mkdir(parents=True)
        input_path = in_dir / "input.tif"

        save_upload(file.file, input_path, settings.max_upload_mb)
        inspect_geotiff(input_path, models.in_channels, settings.max_pixels)

        permanent = None
        if baseline_file is not None:
            baseline_path = in_dir / "baseline.tif"
            save_upload(baseline_file.file, baseline_path, settings.max_upload_mb)
            permanent = svc.read_baseline(baseline_path, input_path)

        try:
            result = models.predict(input_path, out_dir)
            areas = analyze_water(result.mask, result.transform, result.crs, permanent)
        except ModelUnavailable:
            raise HTTPException(503, "The flood model is not loaded, so analyses are unavailable.")
        except ValueError as err:
            raise UploadRejected(422, str(err))

        zones = svc.build_zones(result.mask, result.probability, result.transform, result.crs, permanent)
        analysis_id = svc.store_analysis(
            db, event_id=event_id, source_id=source_id, file_name=name, input_path=input_path,
            band_count=models.in_channels, result=result, areas=areas,
            baseline_method="none" if permanent is None else "jrc", zones=zones)
        db.commit()
        return svc.fetch_analysis(db, analysis_id)
    except Exception:
        db.rollback()                                    # nothing half-saved in the database...
        shutil.rmtree(in_dir, ignore_errors=True)        # ...and no files left behind
        shutil.rmtree(out_dir, ignore_errors=True)
        raise


@router.get("", response_model=list[AnalysisOut])
def list_analyses(
    event_id: Optional[int] = Query(None, ge=1, le=MAX_BIGINT),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Analyses, newest first. Use event_id to see one event's analyses."""
    return svc.list_analyses(db, event_id, limit, offset)


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: int = PathParam(ge=1, le=MAX_BIGINT), db: Session = Depends(get_db)):
    found = svc.fetch_analysis(db, analysis_id)
    if found is None:
        raise HTTPException(404, f"Analysis {analysis_id} not found")
    return found


@router.get("/{analysis_id}/zones")
def get_zones(
    analysis_id: int = PathParam(ge=1, le=MAX_BIGINT),
    zone_type: Optional[ZoneType] = Query(None, description="only this class of polygon"),
    db: Session = Depends(get_db),
):
    """The flood polygons of an analysis as a GeoJSON FeatureCollection (longitude/latitude)."""
    if not _exists(db, "flood_analysis", "analysis_id", analysis_id):
        raise HTTPException(404, f"Analysis {analysis_id} not found")

    sql = ("SELECT zone_id, zone_type, poly_no, n_pixels, area_km2, mean_confidence, "
           "ST_AsGeoJSON(geom, 6) AS geojson FROM flood_zones WHERE analysis_id = :aid")
    params = {"aid": analysis_id}
    if zone_type is not None:
        sql += " AND zone_type = :zt"
        params["zt"] = zone_type
    sql += " ORDER BY zone_type, poly_no"

    features = [{
        "type": "Feature",
        "geometry": json.loads(r["geojson"]),
        "properties": {
            "zone_id": r["zone_id"], "zone_type": r["zone_type"], "poly_no": r["poly_no"],
            "n_pixels": r["n_pixels"], "area_km2": float(r["area_km2"]),
            "mean_confidence": None if r["mean_confidence"] is None else float(r["mean_confidence"]),
        },
    } for r in db.execute(text(sql), params).mappings()]
    return JSONResponse({"type": "FeatureCollection", "features": features}, media_type="application/geo+json")


@router.get("/{analysis_id}/mask")
def download_mask(analysis_id: int = PathParam(ge=1, le=MAX_BIGINT), db: Session = Depends(get_db)):
    """The water mask as a georeferenced GeoTIFF (0 = not water, 1 = water, 255 = no data)."""
    row = db.execute(text("SELECT mask_path FROM flood_analysis WHERE analysis_id = :id"),
                     {"id": analysis_id}).first()
    if row is None:
        raise HTTPException(404, f"Analysis {analysis_id} not found")
    path = svc.resolve_stored(row[0]) if row[0] else None
    if path is None or not path.is_file():
        raise HTTPException(404, "The mask file is no longer available")
    return FileResponse(path, media_type="image/tiff", filename=f"analysis_{analysis_id}_water_mask.tif")
