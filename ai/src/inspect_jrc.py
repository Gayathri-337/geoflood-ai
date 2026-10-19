"""
GeoFlood AI - Phase 11 prep: inspect the JRC permanent-water layer.

Checks the files, their values and alignment with the radar chips, and measures
how much of the labelled water is also marked as water in the JRC layer.
Saves ai/results/jrc_overlap.csv.

Usage (project root):  python -m ai.src.inspect_jrc
"""

import numpy as np
import pandas as pd
import rasterio

from ai.src import config

JRC_DIR = config.RAW_DIR / "JRCWaterHand"
SEP = "=" * 66


def main():
    print(SEP)
    print("  GeoFlood AI - JRC permanent-water layer check")
    print(SEP)

    if not JRC_DIR.exists():
        raise SystemExit(f"Folder not found: {JRC_DIR}\nRun the download commands from Step 11.2.")

    files = sorted(JRC_DIR.glob("*_JRCWaterHand.tif"))
    print(f"\nFiles matching *_JRCWaterHand.tif: {len(files)}")
    if not files:
        print("Names found instead:", [p.name for p in list(JRC_DIR.iterdir())[:5]])
        raise SystemExit("File names differ from what I expected. Send me the line above.")

    rows, seen, skipped = [], set(), 0
    for jp in files:
        chip = jp.name.replace("_JRCWaterHand.tif", "")
        lp = config.LBL_DIR / f"{chip}_LabelHand.tif"
        sp = config.IMG_DIR / f"{chip}_S1Hand.tif"
        if not lp.exists() or not sp.exists():
            skipped += 1
            continue

        with rasterio.open(jp) as src:
            jrc, jbounds, jdtype = src.read(1), src.bounds, src.dtypes[0]
        with rasterio.open(lp) as src:
            label = src.read(1)
        with rasterio.open(sp) as src:
            sbounds = src.bounds

        seen.update(np.unique(jrc).tolist())
        if jrc.shape != label.shape or not np.allclose(tuple(jbounds), tuple(sbounds), atol=1e-6):
            skipped += 1
            continue

        valid = label != -1
        label_water = (label == 1) & valid
        jrc_water = (jrc == 1) & valid
        rows.append({
            "chip": chip,
            "country": chip.split("_")[0],
            "label_water_px": int(label_water.sum()),
            "jrc_water_px": int(jrc_water.sum()),
            "label_and_jrc_px": int((label_water & jrc_water).sum()),
        })

    print(f"Chips compared: {len(rows)}   skipped (missing/misaligned): {skipped}")
    print(f"Data type of the JRC files: {jdtype}")
    print(f"All distinct values found: {sorted(seen)[:12]}")
    if not seen <= {-1, 0, 1, 255}:
        print("\n[WARN] Values are not just -1/0/1/255, so my '== 1 means water' assumption may be wrong.")
        print("       Send me the line above and the dataset README text about JRC.")
        return

    df = pd.DataFrame(rows)
    df.to_csv(config.ROOT / "ai" / "results" / "jrc_overlap.csv", index=False)

    g = df.groupby("country")[["label_water_px", "jrc_water_px", "label_and_jrc_px"]].sum()
    g.loc["ALL"] = g.sum()
    g["labelled_water_also_in_jrc_%"] = (100 * g.label_and_jrc_px / g.label_water_px).round(1)
    g["jrc_only_px"] = g.jrc_water_px - g.label_and_jrc_px
    print("\n--- How much of the labelled water is also JRC water? ---")
    print(g.to_string())
    print("\nHigh % = most labelled water is long-standing water (rivers, lakes).")
    print("Low % = most labelled water is newly flooded land.")
    print(SEP)


if __name__ == "__main__":
    main()
