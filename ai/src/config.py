"""
GeoFlood AI - central configuration.

Every path and constant used by more than one script lives here, so
that training, evaluation, prediction and the backend all agree.
"""

from pathlib import Path

# ai/src/config.py -> parents[2] is the project root
ROOT = Path(__file__).resolve().parents[2]

# --- Raw dataset (Sen1Floods11 hand-labeled subset) ---
RAW_DIR = ROOT / "ai" / "data" / "raw" / "sen1floods11"
IMG_DIR = RAW_DIR / "S1Hand"
LBL_DIR = RAW_DIR / "LabelHand"
SPLIT_DIR = RAW_DIR / "splits"

# --- Processed data and trained models ---
PROCESSED = ROOT / "ai" / "data" / "processed"
MODELS_DIR = ROOT / "ai" / "models"

# split name -> CSV listing (image file, label file) pairs
SPLIT_FILES = {
    "train": "flood_train_data.csv",
    "val": "flood_valid_data.csv",
    "test": "flood_test_data.csv",
    "bolivia": "flood_bolivia_data.csv",  # held-out region, never trained on
}

# --- Image normalisation ---
# Sentinel-1 backscatter in dB. Band 1 is believed to be VV, band 2 VH.
# Values outside these ranges are clipped, then scaled to 0..1.
CLIP_RANGES = [
    (-30.0, 0.0),   # band 1 (VV)
    (-40.0, -5.0),  # band 2 (VH)
]
IN_CHANNELS = 2

# --- Labels ---
# Processed masks: 0 = not flood, 1 = flood, 255 = ignore (no data / invalid)
IGNORE_INDEX = 255
