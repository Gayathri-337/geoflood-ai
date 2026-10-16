"""
GeoFlood AI - PyTorch Dataset and DataLoaders.

Each item is (image, mask, chip_name):
  image : float32 tensor [2, H, W], values 0..1
  mask  : int64 tensor   [H, W],    values 0 (dry), 1 (flood), 255 (ignore)
  chip_name : string, e.g. "India_12345"
"""

import random

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from ai.src import config


class FloodDataset(Dataset):
    def __init__(self, split, augment=False, crop_size=None):
        """
        split     : "train", "val", "test" or "bolivia"
        augment   : random flips / 90-degree rotations (use for training only)
        crop_size : if set, crop to crop_size x crop_size (random when
                    augment=True, centered otherwise)
        """
        if split not in config.SPLIT_FILES:
            raise ValueError(f"Unknown split '{split}'. Choose from {list(config.SPLIT_FILES)}")

        self.img_dir = config.PROCESSED / split / "images"
        self.lbl_dir = config.PROCESSED / split / "masks"
        self.files = sorted(p.name for p in self.img_dir.glob("*.npy"))

        if not self.files:
            raise FileNotFoundError(
                f"No processed chips in {self.img_dir}. Run: python -m ai.src.preprocess_dataset"
            )

        self.augment = augment
        self.crop_size = crop_size

    def __len__(self):
        return len(self.files)

    def _crop(self, img, mask):
        """Crop image [C,H,W] and mask [H,W] to the same square window."""
        _, h, w = img.shape
        size = self.crop_size
        if size >= h and size >= w:
            return img, mask
        if self.augment:
            top = random.randint(0, h - size)
            left = random.randint(0, w - size)
        else:
            top = (h - size) // 2
            left = (w - size) // 2
        return (img[:, top:top + size, left:left + size],
                mask[top:top + size, left:left + size])

    @staticmethod
    def _augment(img, mask):
        """Apply the SAME random flips/rotation to image and mask."""
        if random.random() < 0.5:                     # horizontal flip
            img, mask = img[:, :, ::-1], mask[:, ::-1]
        if random.random() < 0.5:                     # vertical flip
            img, mask = img[:, ::-1, :], mask[::-1, :]
        k = random.randint(0, 3)                      # rotate k * 90 degrees
        if k:
            img = np.rot90(img, k, axes=(1, 2))
            mask = np.rot90(mask, k, axes=(0, 1))
        return img, mask

    def __getitem__(self, idx):
        name = self.files[idx]
        img = np.load(self.img_dir / name)    # float32 [2, H, W]
        mask = np.load(self.lbl_dir / name)   # uint8   [H, W]

        if self.crop_size:
            img, mask = self._crop(img, mask)
        if self.augment:
            img, mask = self._augment(img, mask)

        # Flips/rotations create negatively-strided views; make them contiguous
        img = torch.from_numpy(np.ascontiguousarray(img))
        mask = torch.from_numpy(np.ascontiguousarray(mask).astype(np.int64))
        return img, mask, name[:-4]


def get_dataloaders(
    batch_size=config.TRAIN_BATCH_SIZE,
    crop_size=config.TRAIN_CROP,
    num_workers=config.NUM_WORKERS,
):
    """Return a dict of DataLoaders: train, val, test, bolivia."""
    pin = torch.cuda.is_available()

    train_ds = FloodDataset("train", augment=True, crop_size=crop_size)
    loaders = {
        "train": DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                            num_workers=num_workers, drop_last=True, pin_memory=pin),
    }
    for split in ("val", "test", "bolivia"):
        loaders[split] = DataLoader(
            FloodDataset(split), batch_size=config.EVAL_BATCH_SIZE, shuffle=False,
            num_workers=num_workers, pin_memory=pin,
        )
    return loaders
