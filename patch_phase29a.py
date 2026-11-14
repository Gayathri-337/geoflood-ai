"""
GeoFlood AI - Phase 29a patch. Adds the optional 'acquired_at' (date the satellite took the image)
to the upload, and registers the progression route. Run once from the project root:

    python patch_phase29a.py

Each edit is checked against the exact text it expects. If a file does not look as expected, nothing
in that file is changed and you are told. Running it twice is safe.
"""
from pathlib import Path

EDITS = {
    "backend/main.py": [
        ("from backend.security import access_policy\n",
         "from backend.routers import progression\nfrom backend.security import access_policy\n",
         "from backend.routers import progression"),
        ("app.include_router(report.router, prefix=\"/api\", dependencies=policy)\n",
         "app.include_router(report.router, prefix=\"/api\", dependencies=policy)\n"
         "app.include_router(progression.router, prefix=\"/api\", dependencies=policy)\n",
         "app.include_router(progression.router"),
    ],
    "backend/services/analysis_service.py": [
        ("                   result, areas, baseline_method, zones) -> int:",
         "                   result, areas, baseline_method, zones, acquired_at=None) -> int:",
         "baseline_method, zones, acquired_at=None"),
        ("file_sha256, width_px, height_px, band_count, crs, footprint)\n"
         "        VALUES (:event_id, :source_id, 'event', :file_name, :file_path, :sha, :w, :h, :bands, :crs,\n"
         "                ST_MakeEnvelope",
         "file_sha256, width_px, height_px, band_count, crs, footprint, acquired_at)\n"
         "        VALUES (:event_id, :source_id, 'event', :file_name, :file_path, :sha, :w, :h, :bands, :crs,\n"
         "                ST_MakeEnvelope",
         "footprint, acquired_at)"),
        ("ST_MakeEnvelope(:west, :south, :east, :north, 4326))\n        RETURNING image_id",
         "ST_MakeEnvelope(:west, :south, :east, :north, 4326), :acquired_at)\n        RETURNING image_id",
         ":north, 4326), :acquired_at)"),
        ("        \"west\": west, \"south\": south, \"east\": east, \"north\": north,\n    }).scalar_one()",
         "        \"west\": west, \"south\": south, \"east\": east, \"north\": north,\n"
         "        \"acquired_at\": acquired_at,\n    }).scalar_one()",
         "\"acquired_at\": acquired_at"),
    ],
    "backend/routers/analyses.py": [
        ("from backend.services.inference import ModelService, ModelUnavailable, get_model_service\n",
         "from backend.services.inference import ModelService, ModelUnavailable, get_model_service\n"
         "from backend.services.progression import validate_acquired_at\n",
         "import validate_acquired_at"),
        ("    settings: Settings = Depends(get_settings),\n    models: ModelService = Depends(get_model_service),\n"
         "    db: Session = Depends(get_db),\n):\n    \"\"\"\n    Run the U-Net",
         "    acquired_at: Optional[str] = Form(\n"
         "        None, description=\"Optional: the date (or date and time) the satellite took the image, "
         "for example 2026-10-27. Needed to compare analyses over time.\"),\n"
         "    settings: Settings = Depends(get_settings),\n    models: ModelService = Depends(get_model_service),\n"
         "    db: Session = Depends(get_db),\n):\n    \"\"\"\n    Run the U-Net",
         "acquired_at: Optional[str] = Form("),
        ("    name = clean_filename(file.filename)\n    check_suffix(name)\n",
         "    try:\n        observed_at = validate_acquired_at(acquired_at)\n"
         "    except ValueError as err:\n        raise HTTPException(422, str(err))\n\n"
         "    name = clean_filename(file.filename)\n    check_suffix(name)\n",
         "observed_at = validate_acquired_at"),
        ("baseline_method=\"none\" if permanent is None else \"jrc\", zones=zones)",
         "baseline_method=\"none\" if permanent is None else \"jrc\", zones=zones,\n"
         "            acquired_at=observed_at)",
         "acquired_at=observed_at)"),
    ],
}


def main():
    problems = 0
    for name, edits in EDITS.items():
        path = Path(name)
        if not path.exists():
            print(f"[MISSING] {name} - run this from the project root")
            problems += 1
            continue
        text = path.read_text(encoding="utf-8")
        todo = []
        for old, new, marker in edits:
            if marker in text:
                continue                      # already applied
            if text.count(old) != 1:
                print(f"[STOP] {name}: the text to change was not found exactly once:\n    {old.strip().splitlines()[0]}")
                problems += 1
                todo = None
                break
            todo.append((old, new))
        if todo is None:
            continue
        if not todo:
            print(f"[SKIP] {name}: already patched")
            continue
        for old, new in todo:
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
        print(f"[DONE] {name}: {len(todo)} edit(s)")
    print("\nAll good." if not problems else f"\n{problems} problem(s) - send me the lines above.")


if __name__ == "__main__":
    main()
