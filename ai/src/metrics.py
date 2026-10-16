"""
GeoFlood AI - evaluation metrics for binary flood segmentation.

ConfusionMeter accumulates true/false positives and negatives over many
batches (ignoring 255 pixels) and then computes the metrics once.
Note: for binary pixel classification, Dice and F1 are the same formula,
so they will always be equal. IoU is always lower than Dice.
"""

import torch

from ai.src import config


def _ratio(numerator, denominator):
    return numerator / denominator if denominator > 0 else 0.0


class ConfusionMeter:
    def __init__(self, ignore_index=config.IGNORE_INDEX, threshold=config.THRESHOLD):
        self.ignore_index = ignore_index
        self.threshold = threshold
        self.reset()

    def reset(self):
        self.tp = self.fp = self.fn = self.tn = 0

    @torch.no_grad()
    def update(self, logits, targets):
        """logits: [B,1,H,W]; targets: [B,H,W] with values 0, 1, ignore_index."""
        pred = torch.sigmoid(logits.squeeze(1)) > self.threshold
        valid = targets != self.ignore_index
        truth = targets == 1

        self.tp += int((pred & truth & valid).sum())
        self.fp += int((pred & ~truth & valid).sum())
        self.fn += int((~pred & truth & valid).sum())
        self.tn += int((~pred & ~truth & valid).sum())

    def compute(self):
        tp, fp, fn, tn = self.tp, self.fp, self.fn, self.tn
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        return {
            "iou": _ratio(tp, tp + fp + fn),
            "dice": _ratio(2 * tp, 2 * tp + fp + fn),
            "precision": precision,
            "recall": recall,
            "f1": _ratio(2 * precision * recall, precision + recall),
            "accuracy": _ratio(tp + tn, tp + fp + fn + tn),
        }
