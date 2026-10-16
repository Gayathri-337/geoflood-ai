"""
GeoFlood AI - loss function.

BCE + Dice, computed only on valid pixels (mask != ignore_index).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

from ai.src import config


class BCEDiceLoss(nn.Module):
    def __init__(
        self,
        ignore_index=config.IGNORE_INDEX,
        bce_weight=config.LOSS_BCE_WEIGHT,
        dice_weight=config.LOSS_DICE_WEIGHT,
        pos_weight=config.POS_WEIGHT,
        smooth=1.0,
    ):
        super().__init__()
        self.ignore_index = ignore_index
        self.bce_weight = bce_weight
        self.dice_weight = dice_weight
        self.smooth = smooth
        if pos_weight is not None:
            self.register_buffer("pos_weight", torch.tensor([float(pos_weight)]))
        else:
            self.pos_weight = None

    def forward(self, logits, targets):
        """
        logits  : [B, 1, H, W] raw model output
        targets : [B, H, W]    values 0, 1 or ignore_index
        """
        logits = logits.squeeze(1)
        valid = (targets != self.ignore_index).float()
        n_valid = valid.sum()
        if n_valid == 0:
            return logits.sum() * 0.0  # nothing to learn from; keeps the graph intact

        flood = (targets == 1).float()

        # Binary cross-entropy, averaged over valid pixels only
        bce = F.binary_cross_entropy_with_logits(
            logits, flood, reduction="none", pos_weight=self.pos_weight
        )
        bce = (bce * valid).sum() / n_valid

        # Soft Dice over all valid pixels in the batch
        probs = torch.sigmoid(logits) * valid
        flood = flood * valid
        intersection = (probs * flood).sum()
        dice = (2 * intersection + self.smooth) / (probs.sum() + flood.sum() + self.smooth)
        dice_loss = 1.0 - dice

        return self.bce_weight * bce + self.dice_weight * dice_loss
