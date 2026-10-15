"""
GeoFlood AI - Phase 4: preprocess the whole dataset.

For every chip listed in the train / val / test / bolivia splits:
  - read the GeoTIFF image and label
  - normalise the image, clean the label
  - save both as .npy files under ai/data/processed/<split>/

Usage (from project root):  python -m ai.src.preprocess_dataset
"""

import numpy as np
import pandas as pd
import rasterio
from tqdm import tqdm

from ai.src import config
from ai.src.preprocessing import normalize_image, prepare_label

SEP = "=" * 66


def process_split(name):
    """Process one split and return a dict of summary numbers."""
    csv_path = config.SPLIT_DIR / config.SPLIT_FILES[name]
    if not csv_path.exists():
        raise FileNotFoundError(f"Split file missing: {csv_path}")

    pairs = pd.read_csv(csv_path, header=None)

    img_out = config.PROCESSED / name / "images"
    lbl_out = config.PROCESSED / name / "masks"
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)

    n_flood = n_dry = n_ignore = 0
    vmin, vmax = 1.0, 0.0

    for img_name, lbl_name in tqdm(zip(pairs[0], pairs[1]), total=len(pairs), desc=name):
        chip = img_name.replace("_S1Hand.tif", "")

        with rasterio.open(config.IMG_DIR / img_name) as src:
            img = src.read()
        with rasterio.open(config.LBL_DIR / lbl_name) as src:
            lbl = src.read(1)

        norm, invalid = normalize_image(img)
        mask = prepare_label(lbl, invalid)

        # Safety checks - fail loudly rather than train on bad data
        assert norm.shape[0] == config.IN_CHANNELS, f"{chip}: wrong band count"
        assert norm.shape[1:] == mask.shape, f"{chip}: image/mask size mismatch"
        assert not np.isnan(norm).any(), f"{chip}: NaN survived normalisation"
        assert set(np.unique(mask)) <= {0, 1, config.IGNORE_INDEX}, f"{chip}: bad mask values"

        vmin = min(vmin, float(norm.min()))
        vmax = max(vmax, float(norm.max()))
        n_flood += int((mask == 1).sum())
        n_dry += int((mask == 0).sum())
        n_ignore += int((mask == config.IGNORE_INDEX).sum())

        np.save(img_out / f"{chip}.npy", norm)
        np.save(lbl_out / f"{chip}.npy", mask)

    valid = n_flood + n_dry
    return {
        "split": name,
        "chips": len(pairs),
        "flood_pct_of_valid": round(100 * n_flood / valid, 2),
        "ignored_pct": round(100 * n_ignore / (valid + n_ignore), 2),
        "norm_min": round(vmin, 3),
        "norm_max": round(vmax, 3),
        "_flood": n_flood,
        "_dry": n_dry,
    }


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 4 Preprocessing")
    print(SEP)

    results = [process_split(name) for name in config.SPLIT_FILES]
    table = pd.DataFrame(results)

    print("\n--- Summary ---")
    print(table.drop(columns=["_flood", "_dry"]).to_string(index=False))

    train = table[table["split"] == "train"].iloc[0]
    ratio = train["_dry"] / train["_flood"]
    print("\n--- Class balance in the training split (valid pixels only) ---")
    print(f"  Flood pixels     : {int(train['_flood'])}")
    print(f"  Not-flood pixels : {int(train['_dry'])}")
    print(f"  Dry : flood ratio ~ {ratio:.1f} : 1  (we will use this in Phase 6)")

    print("\nDone. Files saved under:", config.PROCESSED)
    print(SEP)


if __name__ == "__main__":
    main()
