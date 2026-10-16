"""
GeoFlood AI - Phase 5 test: check the Dataset and DataLoaders.

Verifies sizes, tensor shapes, value ranges, that augmentation keeps
image and mask aligned, and saves a picture of one training batch:
  ai/data/processed/batch_check.png

Usage (from project root):  python -m ai.src.test_dataset
"""

import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from matplotlib.colors import ListedColormap

from ai.src import config
from ai.src.dataset import FloodDataset, get_dataloaders

SEP = "=" * 66


def check_augmentation_alignment(n=5):
    """
    Flips and rotations only rearrange pixels, so the count of flood pixels
    and the image mean must not change. If they do, image and mask have
    drifted apart.
    """
    plain = FloodDataset("train")
    aug = FloodDataset("train", augment=True)
    for i in range(n):
        img0, m0, _ = plain[i]
        img1, m1, _ = aug[i]
        assert (m0 == 1).sum() == (m1 == 1).sum(), "flood pixel count changed!"
        assert (m0 == 255).sum() == (m1 == 255).sum(), "ignore pixel count changed!"
        assert torch.isclose(img0.mean(), img1.mean(), atol=1e-5), "image mean changed!"
    print(f"  [OK] augmentation preserved flood/ignore counts and image mean ({n} chips)")


def save_batch_picture(loader):
    images, masks, names = next(iter(loader))
    n = min(4, len(names))
    cmap = ListedColormap(["white", "royalblue", "lightgray"])  # dry, flood, ignore

    fig, axes = plt.subplots(n, 3, figsize=(10, 3.4 * n))
    for r in range(n):
        m = masks[r].numpy()
        code = np.zeros_like(m)
        code[m == 1] = 1
        code[m == 255] = 2
        axes[r, 0].imshow(images[r, 0], cmap="gray", vmin=0, vmax=1)
        axes[r, 1].imshow(images[r, 1], cmap="gray", vmin=0, vmax=1)
        axes[r, 2].imshow(code, cmap=cmap, vmin=0, vmax=2)
        axes[r, 0].set_ylabel(names[r], fontsize=9)
        if r == 0:
            axes[r, 0].set_title("Band 1 (VV)")
            axes[r, 1].set_title("Band 2 (VH)")
            axes[r, 2].set_title("Mask: blue=flood, gray=ignore")
        for c in range(3):
            axes[r, c].set_xticks([])
            axes[r, c].set_yticks([])
    fig.tight_layout()
    out = config.PROCESSED / "batch_check.png"
    fig.savefig(out, dpi=100)
    plt.close(fig)
    print(f"  Saved: {out}")


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 5 DataLoader Test")
    print(SEP)

    loaders = get_dataloaders()

    print("\n--- Dataset sizes ---")
    for name, loader in loaders.items():
        print(f"  {name:<8}: {len(loader.dataset):>4} chips, {len(loader):>3} batches")

    print("\n--- One training batch ---")
    images, masks, names = next(iter(loaders["train"]))
    print(f"  images : {tuple(images.shape)}  {images.dtype}  "
          f"min={images.min():.3f} max={images.max():.3f}")
    print(f"  masks  : {tuple(masks.shape)}  {masks.dtype}  values={torch.unique(masks).tolist()}")
    print(f"  chips  : {list(names)}")
    assert not torch.isnan(images).any(), "NaN in images!"

    print("\n--- One validation batch (full size, no augmentation) ---")
    vimg, vmask, _ = next(iter(loaders["val"]))
    print(f"  images : {tuple(vimg.shape)}")
    print(f"  masks  : {tuple(vmask.shape)}")

    print("\n--- Augmentation alignment ---")
    check_augmentation_alignment()

    print("\n--- Flood share in training batches (first 20 batches) ---")
    flood = valid = 0
    for i, (_, m, _) in enumerate(loaders["train"]):
        flood += int((m == 1).sum())
        valid += int((m != config.IGNORE_INDEX).sum())
        if i == 19:
            break
    print(f"  flood = {100 * flood / valid:.2f}% of valid pixels")

    print("\n--- Time for one full training epoch of loading ---")
    start = time.time()
    for _ in loaders["train"]:
        pass
    print(f"  {time.time() - start:.1f} seconds")

    print("\n--- Batch picture ---")
    save_batch_picture(loaders["train"])
    print(SEP)


if __name__ == "__main__":
    main()
