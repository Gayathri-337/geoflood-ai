
import sys
import platform

# Each entry is (import name, human-readable name, which stage needs it)
PACKAGES = [
    ("numpy",        "NumPy",              "core"),
    ("pandas",       "Pandas",             "core"),
    ("matplotlib",   "Matplotlib",         "core"),
    ("PIL",          "Pillow",             "core"),
    ("sklearn",      "scikit-learn",       "metrics"),
    ("tqdm",         "tqdm",               "core"),
    ("cv2",          "OpenCV",             "image processing"),
    ("rasterio",     "Rasterio",           "satellite imagery"),
    ("shapely",      "Shapely",            "GIS geometry"),
    ("pyproj",       "PyProj",             "GIS projections"),
    ("fiona",        "Fiona",              "GIS file I/O"),
    ("geopandas",    "GeoPandas",          "GIS dataframes"),
    ("torch",        "PyTorch",            "deep learning"),
    ("torchvision",  "TorchVision",        "deep learning"),
    ("fastapi",      "FastAPI",            "backend"),
    ("uvicorn",      "Uvicorn",            "backend"),
    ("sqlalchemy",   "SQLAlchemy",         "database"),
    ("geoalchemy2",  "GeoAlchemy2",        "spatial database"),
    ("psycopg2",     "psycopg2",           "PostgreSQL driver"),
]

SEPARATOR = "=" * 62


def get_version(module):
    """Return a module's version string, or '(unknown)' if it has none."""
    for attribute in ("__version__", "version", "VERSION"):
        value = getattr(module, attribute, None)
        if isinstance(value, str):
            return value
    return "(unknown)"


def check_packages():
    """Import every required package and print a pass/fail line for each."""
    failed = []

    for import_name, display_name, stage in PACKAGES:
        try:
            module = __import__(import_name)
            version = get_version(module)
            print(f"  [OK]   {display_name:<16} {version:<12} ({stage})")
        except ImportError as error:
            print(f"  [FAIL] {display_name:<16} {'---':<12} ({stage})")
            print(f"         reason: {error}")
            failed.append(display_name)

    return failed


def check_geospatial_stack():
    """
    Confirm the GIS libraries actually work together, not just import.
    Builds a small polygon, puts it in a GeoDataFrame, reprojects it,
    and measures its area. This catches broken PROJ/GDAL installations
    that import fine but fail at runtime.
    """
    try:
        import geopandas as gpd
        from shapely.geometry import Polygon

        # A roughly 0.01 x 0.01 degree square near Hyderabad, India
        square = Polygon([
            (78.47, 17.38),
            (78.48, 17.38),
            (78.48, 17.39),
            (78.47, 17.39),
        ])

        # EPSG:4326 is latitude/longitude in degrees
        gdf = gpd.GeoDataFrame({"name": ["test"]}, geometry=[square], crs="EPSG:4326")

        # EPSG:32644 is UTM zone 44N, which uses metres. Area in degrees
        # is meaningless, so we always reproject before measuring.
        gdf_metres = gdf.to_crs("EPSG:32644")
        area_sq_km = gdf_metres.geometry.area.iloc[0] / 1_000_000

        print(f"  [OK]   Created polygon, reprojected, area = {area_sq_km:.4f} sq km")
        return True

    except Exception as error:
        print(f"  [FAIL] Geospatial stack test failed: {error}")
        return False


def check_pytorch():
    """Run a tiny tensor operation and report whether a GPU is visible."""
    try:
        import torch

        a = torch.randn(2, 3)
        b = torch.randn(3, 2)
        product = a @ b

        print(f"  [OK]   Matrix multiply produced shape {tuple(product.shape)}")

        if torch.cuda.is_available():
            print(f"  [OK]   CUDA GPU available: {torch.cuda.get_device_name(0)}")
        else:
            print("  [INFO] No CUDA GPU here. Expected - we train in Colab.")

        return True

    except Exception as error:
        print(f"  [FAIL] PyTorch test failed: {error}")
        return False


def main():
    print(SEPARATOR)
    print("  GeoFlood AI - Phase 1 Environment Verification")
    print(SEPARATOR)

    print(f"\nPython  : {sys.version.split()[0]}")
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Env path: {sys.prefix}")


    if "venv" not in sys.prefix:
        print("\n  [WARN] You may not be inside the virtual environment.")
        print("         Run:  source venv/bin/activate")

    print("\n--- Package imports ---")
    failed = check_packages()

    print("\n--- Geospatial stack test ---")
    gis_ok = check_geospatial_stack()

    print("\n--- PyTorch test ---")
    torch_ok = check_pytorch()

    print("\n" + SEPARATOR)
    if not failed and gis_ok and torch_ok:
        print("  RESULT: Phase 1 environment is ready.")
    else:
        print("  RESULT: Setup incomplete.")
        if failed:
            print("  Missing packages: " + ", ".join(failed))
        print("  Fix the failures above, then run this script again.")
    print(SEPARATOR)


if __name__ == "__main__":
    main()