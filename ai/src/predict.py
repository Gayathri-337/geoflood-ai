"""
GeoFlood AI - Phase 9: prediction module (reused later by the FastAPI backend).

Usage from Python:
    from ai.src.predict import get_predictor
    result = get_predictor().predict_file("scene.tif", out_dir="outputs/")
    result.stats       # dict of numbers
    result.mask        # uint8 array: 0 = dry, 1 = flood, 255 = no data

Usage from the command line (project root):
    python -m ai.src.predict --input some_chip.tif --out-dir ai/results/predictions

Input requirements: a GeoTIFF with 2 bands (VV, VH) of Sentinel-1 backscatter in dB,
the same convention as the Sen1Floods11 training chips.
"""

import argparse
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
import torch

from ai.src import config
from ai.src.model import UNet
from ai.src.preprocessing import normalize_image

DEFAULT_CHECKPOINT = config.MODELS_DIR / "unet_flood_best.pth"
NODATA = config.IGNORE_INDEX   # value used for "no data" in the output mask (255)


@dataclass
class PredictionResult:
    mask: np.ndarray            # uint8 [H, W]: 0 dry, 1 flood, 255 no data
    probability: np.ndarray     # float32 [H, W]: flood probability (NaN where no data)
    transform: object           # affine transform of the input (None if not from a file)
    crs: object                 # coordinate reference system of the input
    stats: dict
    mask_path: Path = None
    probability_path: Path = None


class FloodPredictor:
    def __init__(self, checkpoint_path=DEFAULT_CHECKPOINT, device=None,
                 threshold=None, tile_size=512, overlap=64):
        checkpoint_path = Path(checkpoint_path)
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Model checkpoint not found: {checkpoint_path}")
        if tile_size % 16 != 0:
            raise ValueError("tile_size must be divisible by 16")
        if not 0 <= overlap < tile_size:
            raise ValueError("overlap must be between 0 and tile_size")

        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        ckpt = torch.load(checkpoint_path, map_location=self.device)

        mc = ckpt["model_config"]
        self.model = UNet(mc["in_channels"], mc["base_channels"]).to(self.device)
        self.model.load_state_dict(ckpt["model_state"])
        self.model.eval()

        self.in_channels = mc["in_channels"]
        self.clip_ranges = [tuple(r) for r in ckpt["clip_ranges"]]   # from training, not config.py
        self.threshold = float(threshold if threshold is not None else ckpt["threshold"])
        self.tile_size = tile_size
        self.overlap = overlap
        self.checkpoint_name = checkpoint_path.name

    # ------------------------------------------------------------------ core
    @staticmethod
    def _starts(length, tile, stride):
        """Start positions of tiles along one axis, making sure the last tile reaches the end."""
        if length <= tile:
            return [0]
        starts = list(range(0, length - tile + 1, stride))
        if starts[-1] != length - tile:
            starts.append(length - tile)
        return starts

    def predict_array(self, img_db):
        """
        img_db : float array [C, H, W] of backscatter in dB (NaN allowed for no data).
        Returns (probability [H, W] float32, valid [H, W] bool).
        """
        if img_db.ndim != 3 or img_db.shape[0] != self.in_channels:
            raise ValueError(f"Expected an array of shape [{self.in_channels}, H, W], "
                             f"got {tuple(img_db.shape)}")

        h, w = img_db.shape[1:]
        norm, invalid = normalize_image(img_db, self.clip_ranges)

        # The network needs sizes divisible by 16: pad, then crop the result back
        pad_h, pad_w = (-h) % 16, (-w) % 16
        if pad_h or pad_w:
            norm = np.pad(norm, ((0, 0), (0, pad_h), (0, pad_w)), mode="edge")
        hp, wp = norm.shape[1:]

        th, tw = min(self.tile_size, hp), min(self.tile_size, wp)
        stride = max(self.tile_size - self.overlap, 16)

        total = np.zeros((hp, wp), dtype=np.float32)
        count = np.zeros((hp, wp), dtype=np.float32)
        with torch.no_grad():
            for top in self._starts(hp, th, stride):
                for left in self._starts(wp, tw, stride):
                    tile = np.ascontiguousarray(norm[:, top:top + th, left:left + tw])
                    x = torch.from_numpy(tile).unsqueeze(0).to(self.device)
                    p = torch.sigmoid(self.model(x))[0, 0].cpu().numpy()
                    total[top:top + th, left:left + tw] += p      # overlaps are averaged
                    count[top:top + th, left:left + tw] += 1.0

        probability = (total / count)[:h, :w]
        return probability, ~invalid

    def _make_result(self, img_db, transform, crs, extra_warnings=()):
        prob, valid = self.predict_array(img_db)
        h, w = prob.shape

        mask = np.full((h, w), NODATA, dtype=np.uint8)
        mask[valid] = (prob[valid] > self.threshold).astype(np.uint8)
        flood = mask == 1

        n_valid = int(valid.sum())
        n_flood = int(flood.sum())
        warnings = list(extra_warnings)
        if n_valid < 0.5 * h * w:
            warnings.append(f"Only {100 * n_valid / (h * w):.0f}% of pixels contain valid data.")
        if n_valid:
            sample = img_db[:, valid][:, ::50]
            for b in range(sample.shape[0]):
                med = float(np.median(sample[b]))
                if not -45.0 <= med <= 10.0:
                    warnings.append(f"Band {b + 1} median is {med:.1f}, which does not look like "
                                    "dB backscatter. Was the image converted to dB?")

        stats = {
            "height": h, "width": w,
            "valid_pixels": n_valid,
            "flood_pixels": n_flood,
            "flood_pct_of_valid": round(100 * n_flood / n_valid, 3) if n_valid else 0.0,
            "mean_flood_confidence": round(float(prob[flood].mean()), 4) if n_flood else 0.0,
            "threshold": self.threshold,
            "model_checkpoint": self.checkpoint_name,
            "warnings": warnings,
        }
        probability = np.where(valid, prob, np.nan).astype(np.float32)
        return PredictionResult(mask, probability, transform, crs, stats)

    # ------------------------------------------------------------------ files
    def predict_file(self, input_path, out_dir=None, save_probability=True):
        """Predict from a GeoTIFF; optionally save georeferenced mask/probability GeoTIFFs."""
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        try:
            src = rasterio.open(input_path)
        except rasterio.errors.RasterioIOError as err:
            raise ValueError(f"'{input_path.name}' is not a readable raster image: {err}")

        with src:
            if src.count != self.in_channels:
                raise ValueError(f"'{input_path.name}' has {src.count} band(s); the model needs "
                                 f"{self.in_channels} (Sentinel-1 VV and VH in dB).")
            # Pixels flagged as no-data in the file become NaN
            data = src.read(masked=True).astype("float32").filled(np.nan)
            transform, crs = src.transform, src.crs

        warnings = []
        if crs is None:
            warnings.append("The image has no coordinate system, so the outputs are not georeferenced.")

        result = self._make_result(data, transform, crs, warnings)

        if out_dir is not None:
            out_dir = Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            h, w = result.mask.shape
            base = dict(driver="GTiff", height=h, width=w, count=1,
                        crs=crs, transform=transform, compress="lzw")

            result.mask_path = out_dir / f"{input_path.stem}_floodmask.tif"
            with rasterio.open(result.mask_path, "w", dtype="uint8", nodata=NODATA, **base) as dst:
                dst.write(result.mask, 1)

            if save_probability:
                result.probability_path = out_dir / f"{input_path.stem}_floodprob.tif"
                with rasterio.open(result.probability_path, "w", dtype="float32",
                                   nodata=float("nan"), **base) as dst:
                    dst.write(result.probability, 1)
        return result


@lru_cache(maxsize=1)
def get_predictor(checkpoint_path=str(DEFAULT_CHECKPOINT)):
    """Load the model once and reuse it (the FastAPI backend will call this)."""
    return FloodPredictor(checkpoint_path)


def main():
    p = argparse.ArgumentParser(description="Predict flood extent for a 2-band Sentinel-1 GeoTIFF")
    p.add_argument("--input", required=True)
    p.add_argument("--out-dir", default=str(config.ROOT / "ai" / "results" / "predictions"))
    p.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    p.add_argument("--threshold", type=float, default=None)
    args = p.parse_args()

    result = FloodPredictor(args.checkpoint, threshold=args.threshold).predict_file(
        args.input, out_dir=args.out_dir)

    print(json.dumps(result.stats, indent=2))
    print(f"\nMask saved       : {result.mask_path}")
    print(f"Probability saved: {result.probability_path}")
    print("Mask values: 0 = not flood, 1 = flood, 255 = no data")


if __name__ == "__main__":
    main()
