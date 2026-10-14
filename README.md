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