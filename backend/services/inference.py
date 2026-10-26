"""
GeoFlood AI backend - the model service.

Loads the U-Net once (at server start) and runs predictions one at a time.
"""

import logging
import threading
from pathlib import Path

from fastapi import Request

from ai.src import config
from ai.src.predict import FloodPredictor

log = logging.getLogger("uvicorn.error")


class ModelUnavailable(Exception):
    """The model could not be loaded, so predictions are not possible."""


class ModelService:
    def __init__(self, checkpoint):
        self.checkpoint = Path(checkpoint)
        self.predictor = None
        self.error = None
        self._lock = threading.Lock()      # one prediction at a time

    def load(self):
        try:
            self.predictor = FloodPredictor(self.checkpoint)
            self.error = None
            log.info("Flood model loaded: %s on %s (threshold %s)",
                     self.checkpoint.name, self.predictor.device, self.predictor.threshold)
        except FileNotFoundError:
            self.predictor, self.error = None, "Model checkpoint file not found."
            log.warning("Model checkpoint not found: %s", self.checkpoint)
        except Exception:
            self.predictor, self.error = None, "The model could not be loaded (see the server log)."
            log.exception("Model failed to load")

    @property
    def loaded(self) -> bool:
        return self.predictor is not None

    @property
    def in_channels(self) -> int:
        return self.predictor.in_channels if self.predictor else config.IN_CHANNELS

    def predict(self, input_path, out_dir):
        """Run the model on a GeoTIFF. Returns the PredictionResult from ai.src.predict."""
        if self.predictor is None:
            raise ModelUnavailable(self.error or "The model is not loaded.")
        with self._lock:
            return self.predictor.predict_file(input_path, out_dir=out_dir)

    def describe(self) -> dict:
        p = self.predictor
        return {
            "status": "ok" if p else "unavailable",
            "loaded": p is not None,
            "checkpoint": self.checkpoint.name,
            "device": str(p.device) if p else None,
            "threshold": p.threshold if p else None,
            "tile_size": p.tile_size if p else None,
            "detail": self.error,
        }


def get_model_service(request: Request) -> ModelService:
    return request.app.state.model_service
