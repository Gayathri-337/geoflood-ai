
import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import torch

from ai.src import config
from ai.src.dataset import get_dataloaders
from ai.src.losses import BCEDiceLoss
from ai.src.metrics import ConfusionMeter
from ai.src.model import UNet


def parse_args():
    p = argparse.ArgumentParser(description="Train the GeoFlood U-Net")
    p.add_argument("--epochs", type=int, default=60)
    p.add_argument("--batch-size", type=int, default=config.TRAIN_BATCH_SIZE)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--patience", type=int, default=15, help="early-stopping patience (epochs)")
    p.add_argument("--out-dir", type=str, default=str(config.MODELS_DIR))
    p.add_argument("--resume", action="store_true", help="continue from last.pth if it exists")
    p.add_argument("--max-batches", type=int, default=0,
                   help="debug only: use at most this many batches per loader")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def train_one_epoch(model, loader, loss_fn, optimizer, device, max_batches=0):
    model.train()
    total, count = 0.0, 0
    for i, (images, masks, _) in enumerate(loader):
        if max_batches and i >= max_batches:
            break
        images = images.to(device, non_blocking=True)
        masks = masks.to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)
        loss = loss_fn(model(images), masks)
        loss.backward()
        optimizer.step()

        total += loss.item() * images.size(0)
        count += images.size(0)
    return total / count


@torch.no_grad()
def validate(model, loader, loss_fn, device, max_batches=0):
    model.eval()
    meter = ConfusionMeter()
    total, count = 0.0, 0
    for i, (images, masks, _) in enumerate(loader):
        if max_batches and i >= max_batches:
            break
        images = images.to(device, non_blocking=True)
        masks = masks.to(device, non_blocking=True)

        logits = model(images)
        total += loss_fn(logits, masks).item() * images.size(0)
        count += images.size(0)
        meter.update(logits, masks)
    return total / count, meter.compute()


def main():
    args = parse_args()
    set_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Device: {device}" + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))
    print(f"Saving to: {out_dir}")

    loaders = get_dataloaders(batch_size=args.batch_size)
    print(f"Train chips: {len(loaders['train'].dataset)}   Val chips: {len(loaders['val'].dataset)}")

    model = UNet(config.IN_CHANNELS, config.UNET_BASE_CHANNELS).to(device)
    loss_fn = BCEDiceLoss().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=0.5, patience=5
    )

    history, best_iou, no_improve, start_epoch = [], -1.0, 0, 1
    last_path = out_dir / "last.pth"
    best_path = out_dir / "unet_flood_best.pth"

    if args.resume and last_path.exists():
        ckpt = torch.load(last_path, map_location=device)
        model.load_state_dict(ckpt["model_state"])
        optimizer.load_state_dict(ckpt["optimizer_state"])
        scheduler.load_state_dict(ckpt["scheduler_state"])
        history = ckpt["history"]
        best_iou = ckpt["best_iou"]
        no_improve = ckpt["no_improve"]
        start_epoch = ckpt["epoch"] + 1
        print(f"Resumed from epoch {ckpt['epoch']} (best val IoU so far {best_iou:.4f})")

    if start_epoch > args.epochs:
        print(f"Already trained for {start_epoch - 1} epochs; raise --epochs to train more.")
        return

    for epoch in range(start_epoch, args.epochs + 1):
        t0 = time.time()
        lr_used = optimizer.param_groups[0]["lr"]

        train_loss = train_one_epoch(model, loaders["train"], loss_fn, optimizer, device, args.max_batches)
        val_loss, m = validate(model, loaders["val"], loss_fn, device, args.max_batches)
        scheduler.step(m["iou"])

        history.append({
            "epoch": epoch, "train_loss": train_loss, "val_loss": val_loss,
            "val_iou": m["iou"], "val_dice": m["dice"], "val_precision": m["precision"],
            "val_recall": m["recall"], "val_f1": m["f1"], "lr": lr_used,
        })

        marker = ""
        if m["iou"] > best_iou:
            best_iou, no_improve, marker = m["iou"], 0, "  <- best"
            torch.save({
                "model_state": model.state_dict(),
                "epoch": epoch,
                "val_metrics": m,
                "model_config": {"in_channels": config.IN_CHANNELS,
                                 "base_channels": config.UNET_BASE_CHANNELS},
                "clip_ranges": [list(r) for r in config.CLIP_RANGES],
                "threshold": config.THRESHOLD,
            }, best_path)
        else:
            no_improve += 1

        torch.save({
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "scheduler_state": scheduler.state_dict(),
            "epoch": epoch, "history": history,
            "best_iou": best_iou, "no_improve": no_improve,
        }, last_path)
        with open(out_dir / "history.json", "w") as f:
            json.dump(history, f, indent=2)

        print(f"Epoch {epoch:>3}/{args.epochs} | train {train_loss:.4f} | val {val_loss:.4f} | "
              f"IoU {m['iou']:.4f} Dice {m['dice']:.4f} P {m['precision']:.4f} R {m['recall']:.4f} | "
              f"lr {lr_used:.1e} | {time.time() - t0:.0f}s{marker}")

        if no_improve >= args.patience:
            print(f"Early stopping: no improvement for {args.patience} epochs.")
            break

    best = max(history, key=lambda r: r["val_iou"])
    print(f"\nBest epoch: {best['epoch']}  val IoU {best['val_iou']:.4f}  Dice {best['val_dice']:.4f}  "
          f"precision {best['val_precision']:.4f}  recall {best['val_recall']:.4f}")
    print(f"Best model saved at: {best_path}")


if __name__ == "__main__":
    main()
