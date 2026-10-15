
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ai" / "data" / "raw" / "sen1floods11"

# Select a sample listed in the official training split
image_path = DATA / "S1Hand" / "Ghana_103272_S1Hand.tif"
label_path = DATA / "LabelHand" / "Ghana_103272_LabelHand.tif"

with rasterio.open(image_path) as src:
    image = src.read()
    print("Image shape:", image.shape)
    print("Image bands:", src.count)

with rasterio.open(label_path) as src:
    mask = src.read(1)
    print("Mask shape:", mask.shape)
    print("Mask classes:", np.unique(mask, return_counts=True))

# Display the two radar bands separately, the flood mask, and an overlay
fig, axes = plt.subplots(1, 4, figsize=(18, 5))

axes[0].imshow(image[0], cmap="gray")
axes[0].set_title("SAR Band 1")

axes[1].imshow(image[1], cmap="gray")
axes[1].set_title("SAR Band 2")

# -1 means unlabeled/invalid in this sample; show it separately
display_mask = np.ma.masked_where(mask == -1, mask)
axes[2].imshow(display_mask, cmap="Blues", vmin=0, vmax=1)
axes[2].set_title("Flood Label Mask")

# Show the first radar band with the flood labels overlaid
axes[3].imshow(image[0], cmap="gray")
axes[3].imshow(
    np.ma.masked_where(mask != 1, mask),
    cmap="autumn",
    vmin=0,
    vmax=1,
    alpha=0.7,
)
axes[3].set_title("Flood Areas Overlay")

for ax in axes:
    ax.axis("off")

plt.tight_layout()

output_dir = ROOT / "ai" / "data" / "processed"
output_dir.mkdir(parents=True, exist_ok=True)

output_path = output_dir / "dataset_visualization.png"
plt.savefig(output_path, dpi=150, bbox_inches="tight")
print("Saved visualization to:", output_path)

plt.show()
