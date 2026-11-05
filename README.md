# GeoFlood AI

Intelligent flood mapping and disaster monitoring using satellite imagery.

Final-year project. Detects flooded regions in satellite images using a U-Net segmentation model, converts predictions into GIS polygons, analyses impact on villages, roads, agriculture and infrastructure, and presents the results on an interactive web dashboard.

## Stack

| Layer | Technology |
|---|---|
| Model | PyTorch, U-Net |
| Imagery | Rasterio, OpenCV, NumPy |
| GIS | GeoPandas, Shapely |
| Database | PostgreSQL + PostGIS |
| Backend | FastAPI |
| Frontend | React, Leaflet, Bootstrap |

## Status

- [x] Phase 1 - Environment setup
- [ ] Phase 2 - Dataset acquisition
- [ ] Phase 3 - Data exploration

## Local setup

```bash
source venv/bin/activate
python -m pip install -r requirements.txt
python verify_setup.py
```

## OpenStreetMap coverage (Phase 21)
- `gis/osm_coverage.py` is the main scanner: all 68 India chips, results in `ai/results/osm_coverage_india.csv`.
- `ai/src/scan_osm_coverage.py` is an independent cross-check on the 14 test chips (`ai/results/osm_coverage.csv`).
13 of 14 chips give identical counts; `India_570384` has 115 roads there vs 117 in the main scan (cause not established).
