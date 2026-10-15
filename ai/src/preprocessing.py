"""
GeoFlood AI - preprocessing functions shared by training and inference.

IMPORTANT: anything that changes here changes the model's inputs. If you
edit these functions after training, you must retrain the model.
"""

import numpy as np

from ai.src.config import CLIP_RANGES, IGNORE_INDEX


def normalize_image(img):
    """
    Convert a raw SAR chip into a clean network input.

    Parameters
    ----------
    img : array of shape [2, H, W], backscatter in dB (may contain NaN/inf)

    Returns
    -------
    normalized : float32 array [2, H, W], values in 0..1, never NaN
    invalid    : bool array [H, W], True where any band was NaN/inf
    """
    img = img.astype("float32")
    invalid = ~np.isfinite(img).all(axis=0)

    out = np.empty_like(img)
    for b, (lo, hi) in enumerate(CLIP_RANGES):
        band = np.nan_to_num(img[b], nan=lo, posinf=hi, neginf=lo)
        band = np.clip(band, lo, hi)
        out[b] = (band - lo) / (hi - lo)

    # Invalid pixels get a neutral value; the label marks them "ignore"
    out[:, invalid] = 0.0
    return out, invalid


def prepare_label(label, invalid=None):
    """
    Convert a raw label (-1 / 0 / 1) into 0 / 1 / 255.

    Parameters
    ----------
    label   : int array [H, W] with values -1 (no data), 0 (dry), 1 (flood)
    invalid : optional bool array [H, W]; these pixels are also ignored
    """
    out = np.full(label.shape, IGNORE_INDEX, dtype=np.uint8)
    out[label == 0] = 0
    out[label == 1] = 1
    if invalid is not None:
        out[invalid] = IGNORE_INDEX
    return out
