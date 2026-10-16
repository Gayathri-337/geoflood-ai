"""
GeoFlood AI - Phase 6 test: model, loss, metrics, and an overfit check.

Usage (from project root):  python -m ai.src.test_model
"""

import time

import torch

from ai.src import config
from ai.src.dataset import FloodDataset
from ai.src.losses import BCEDiceLoss
from ai.src.metrics import ConfusionMeter
from ai.src.model import UNet

SEP = "=" * 66


def test_model():
    model = UNet(config.IN_CHANNELS, config.UNET_BASE_CHANNELS).eval()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"  Parameters: {n_params:,}")

    for shape in [(2, 2, 256, 256), (1, 2, 512, 512)]:
        with torch.no_grad():
            out = model(torch.randn(*shape))
        expected = (shape[0], 1, shape[2], shape[3])
        assert tuple(out.shape) == expected, f"wrong output shape {tuple(out.shape)}"
        print(f"  [OK] input {shape} -> output {tuple(out.shape)}")

    try:
        model(torch.randn(1, 2, 250, 250))
        raise AssertionError("size not divisible by 16 should have raised an error")
    except ValueError:
        print("  [OK] size 250x250 correctly rejected")


def test_loss():
    torch.manual_seed(0)
    loss_fn = BCEDiceLoss()
    logits = torch.randn(2, 1, 64, 64)
    targets = torch.randint(0, 2, (2, 64, 64))
    targets[:, :16, :] = config.IGNORE_INDEX

    base = loss_fn(logits, targets)
    assert torch.isfinite(base), "loss is not finite"
    print(f"  [OK] loss on random data = {base.item():.4f}")

    # Changing the prediction ONLY at ignored pixels must not change the loss
    changed = logits.clone()
    changed[:, :, :16, :] += 100.0
    assert torch.isclose(base, loss_fn(changed, targets)), "ignored pixels affect the loss!"
    print("  [OK] pixels marked 255 do not affect the loss")

    all_ignored = torch.full((2, 64, 64), config.IGNORE_INDEX)
    assert loss_fn(logits, all_ignored).item() == 0.0
    print("  [OK] a batch with only ignored pixels gives zero loss (no crash)")


def test_metrics():
    # Hand-checkable case: truth [1,1,0,0,ignore], prediction [1,0,1,0,1]
    # -> tp=1, fn=1, fp=1, tn=1 (the 5th pixel is ignored)
    targets = torch.tensor([[[1, 1, 0, 0, config.IGNORE_INDEX]]])
    logits = torch.tensor([[[[5.0, -5.0, 5.0, -5.0, 5.0]]]])
    meter = ConfusionMeter()
    meter.update(logits, targets)
    r = meter.compute()
    assert (meter.tp, meter.fp, meter.fn, meter.tn) == (1, 1, 1, 1)
    assert abs(r["iou"] - 1 / 3) < 1e-9 and abs(r["dice"] - 0.5) < 1e-9
    assert abs(r["precision"] - 0.5) < 1e-9 and abs(r["recall"] - 0.5) < 1e-9
    print("  [OK] hand-checked example gives IoU=1/3, Dice=F1=0.5, precision=recall=0.5")

    # Perfect prediction -> everything 1.0
    truth = torch.randint(0, 2, (1, 32, 32))
    perfect = (truth.float() * 20 - 10).unsqueeze(1)
    meter = ConfusionMeter()
    meter.update(perfect, truth)
    assert meter.compute()["iou"] == 1.0
    print("  [OK] perfect prediction gives IoU = 1.0")


def pick_flood_crops(n=4, size=128, stride=64):
    """Find n training crops (size x size) that contain a decent amount of flood."""
    ds = FloodDataset("train")
    imgs, masks = [], []
    for i in range(len(ds)):
        img, mask, _ = ds[i]
        best, best_frac = None, 0.0
        for top in range(0, 512 - size + 1, stride):
            for left in range(0, 512 - size + 1, stride):
                m = mask[top:top + size, left:left + size]
                valid = int((m != config.IGNORE_INDEX).sum())
                if valid < 0.9 * size * size:
                    continue
                frac = int((m == 1).sum()) / valid
                if frac > best_frac:
                    best, best_frac = (top, left), frac
        if best is not None and best_frac >= 0.10:
            t, l = best
            imgs.append(img[:, t:t + size, l:l + size])
            masks.append(mask[t:t + size, l:l + size])
        if len(imgs) == n:
            break
    if len(imgs) < n:
        raise RuntimeError("could not find enough flooded crops")
    return torch.stack(imgs), torch.stack(masks)


def test_overfit(steps=30):
    torch.manual_seed(0)
    images, masks = pick_flood_crops()
    flood_pct = 100 * (masks == 1).sum().item() / (masks != config.IGNORE_INDEX).sum().item()
    print(f"  Using 4 crops of 128x128 ({flood_pct:.1f}% flood). Training {steps} steps on CPU...")

    model = UNet(config.IN_CHANNELS, config.UNET_BASE_CHANNELS).train()
    loss_fn = BCEDiceLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    meter = ConfusionMeter()

    first = last = None
    start = time.time()
    for step in range(1, steps + 1):
        optimizer.zero_grad()
        logits = model(images)
        loss = loss_fn(logits, masks)
        loss.backward()
        optimizer.step()

        first = first if first is not None else loss.item()
        last = loss.item()
        if step == 1 or step % 5 == 0:
            print(f"    step {step:>3}  loss = {loss.item():.4f}")
        if step == steps:
            meter.update(logits.detach(), masks)

    print(f"  Time: {time.time() - start:.0f} s")
    r = meter.compute()
    print(f"  Final-step metrics on these 4 crops: IoU={r['iou']:.3f} "
          f"Dice={r['dice']:.3f} precision={r['precision']:.3f} recall={r['recall']:.3f}")

    if last < 0.8 * first:
        print(f"  [OK] loss fell from {first:.3f} to {last:.3f}: the model can learn")
    else:
        print(f"  [WARN] loss only went {first:.3f} -> {last:.3f}. Send me this output.")


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 6 Model / Loss / Metrics Test")
    print(SEP)
    print("\n--- U-Net ---")
    test_model()
    print("\n--- Loss ---")
    test_loss()
    print("\n--- Metrics ---")
    test_metrics()
    print("\n--- Overfit test (real data) ---")
    test_overfit()
    print(SEP)


if __name__ == "__main__":
    main()
