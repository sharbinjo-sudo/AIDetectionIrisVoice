"""Dedicated face anti-spoofing (presentation-attack detection) engine.

This module deliberately does **not** reuse SCRFD detection confidence as a
liveness signal: a detector score only says a face-like region was located, not
that the region is a live human. Liveness is produced by a separate classifier
evaluated on the cropped face and is reported explicitly so callers can gate
registration and login on real presentation-attack evidence.

The classifier is a local ONNX model (a MiniFASNet-style PAD network by
default). It runs offline against `backend/trained_models/face`; if the asset
is missing the engine reports ``UNAVAILABLE`` and the workflow fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
from threading import Lock

from django.conf import settings

from .exceptions import BiometricProcessingError, ModelUnavailableError
from .model_assets import ensure_remote_asset

LIVENESS_VALID_REASON = "LIVENESS_VALID"
LIVENESS_SPOOF_REASON = "LIVENESS_SPOOF_DETECTED"
LIVENESS_UNAVAILABLE_REASON = "LIVENESS_MODEL_UNAVAILABLE"
LIVENESS_NOT_EVALUATED_REASON = "LIVENESS_NOT_EVALUATED"
LIVENESS_ERROR_REASON = "LIVENESS_ERROR"


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _softmax(values: list[float]) -> list[float]:
    if not values:
        return []
    largest = max(values)
    exponentials = [math.exp(value - largest) for value in values]
    total = sum(exponentials)
    if total <= 1e-12:
        return [1.0 / len(values)] * len(values)
    return [value / total for value in exponentials]


@dataclass(frozen=True)
class LivenessResult:
    """Structured anti-spoofing outcome, never conflated with detection."""

    evaluated: bool
    passed: bool
    live_score: float
    spoof_score: float
    threshold: float
    model: str | None
    status: str  # LIVE | SPOOF | UNAVAILABLE | ERROR | NOT_EVALUATED
    reason_code: str
    message: str

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "passed": self.passed,
            "evaluated": self.evaluated,
            "live_score": round(self.live_score, 4),
            "spoof_score": round(self.spoof_score, 4),
            "threshold": self.threshold,
            "anti_spoof_model": self.model,
            "reason_code": self.reason_code,
            "message": self.message,
        }


def not_evaluated_result(
    reason_code: str = LIVENESS_NOT_EVALUATED_REASON,
    message: str = "Liveness was not evaluated.",
) -> LivenessResult:
    return LivenessResult(
        evaluated=False,
        passed=False,
        live_score=0.0,
        spoof_score=0.0,
        threshold=float(settings.FACE_LIVENESS_THRESHOLD),
        model=None,
        status="NOT_EVALUATED",
        reason_code=reason_code,
        message=message,
    )


def error_result(
    message: str,
    reason_code: str = LIVENESS_ERROR_REASON,
) -> LivenessResult:
    """Report an anti-spoofing runtime failure explicitly (never a pass)."""
    return LivenessResult(
        evaluated=False,
        passed=False,
        live_score=0.0,
        spoof_score=0.0,
        threshold=float(settings.FACE_LIVENESS_THRESHOLD),
        model=None,
        status="ERROR",
        reason_code=reason_code,
        message=message,
    )


class FaceLivenessEngine:
    """Local ONNX presentation-attack classifier (MiniFASNet-compatible)."""

    name = "Face anti-spoofing ONNX"

    def __init__(self):
        self._cv2 = None
        self._np = None
        self._net = None
        self._load_error: Exception | None = None
        self._lock = Lock()
        self._model_path = self._resolve_model_path()
        self._model_name = settings.FACE_LIVENESS_MODEL_NAME

        # Optional provisioning outside offline mode. Never downloaded while
        # authenticating in an offline-first deployment.
        if (
            (self._model_path is None or not Path(self._model_path).exists())
            and settings.FACE_LIVENESS_MODEL_URL
            and not settings.BIOMETRIC_OFFLINE_MODE
        ):
            try:
                self._model_path = str(
                    ensure_remote_asset(
                        destination=Path(settings.FACE_LIVENESS_MODEL_PATH),
                        description="face anti-spoofing model",
                        urls=[settings.FACE_LIVENESS_MODEL_URL],
                    )
                )
            except ModelUnavailableError as exc:
                self._load_error = exc

        if self._model_path is None or not Path(self._model_path).exists():
            self._load_error = FileNotFoundError(
                "A dedicated face anti-spoofing ONNX model was not found. "
                f"Looked in {settings.FACE_LIVENESS_MODEL_DIR} and "
                f"{settings.FACE_LIVENESS_MODEL_PATH}."
            )
            return

        try:
            import cv2
            import numpy as np

            self._cv2 = cv2
            self._np = np
            self._net = cv2.dnn.readNetFromONNX(str(self._model_path))
        except Exception as exc:  # pragma: no cover - depends on local runtime
            self._load_error = exc
            self._net = None

    @staticmethod
    def _candidate_names() -> tuple[str, ...]:
        return (
            Path(settings.FACE_LIVENESS_MODEL_PATH).name,
            "minifasnet_v2.onnx",
            "minifasnet.onnx",
            "antispoof.onnx",
            "anti_spoof.onnx",
            "liveness.onnx",
            "face_antispoofing.onnx",
        )

    def _resolve_model_path(self) -> str | None:
        configured = Path(settings.FACE_LIVENESS_MODEL_PATH)
        if configured.exists():
            return str(configured)

        search_dirs = [
            configured.parent,
            Path(settings.FACE_LIVENESS_MODEL_DIR),
        ]
        for directory in search_dirs:
            for name in self._candidate_names():
                candidate = directory / name
                if candidate.exists():
                    return str(candidate)
        return str(configured)

    @property
    def ready(self) -> bool:
        return self._net is not None and self._cv2 is not None and self._np is not None

    def health(self) -> dict:
        return {
            "ready": self.ready,
            "name": self.name if self.ready else "Face anti-spoofing (unavailable)",
            "mode": "local_onnx" if self.ready else "unavailable",
            "source": str(self._model_path) if self._model_path else None,
            "detail": None if self.ready else str(self._load_error),
            "required": bool(settings.FACE_LIVENESS_REQUIRED),
            "threshold": settings.FACE_LIVENESS_THRESHOLD,
        }

    def _ensure_ready(self) -> None:
        if not self.ready:
            raise ModelUnavailableError(
                "The dedicated face anti-spoofing model is not available. "
                "Provision a MiniFASNet-compatible ONNX file under "
                f"{settings.FACE_LIVENESS_MODEL_DIR} (or configure "
                f"FACE_LIVENESS_MODEL_PATH). Detail: {self._load_error}"
            )

    def _square_face_crop(self, image, bbox):
        assert self._cv2 is not None
        height, width = image.shape[:2]
        x0, y0, x1, y1 = [float(value) for value in bbox]
        center_x = (x0 + x1) * 0.5
        center_y = (y0 + y1) * 0.5
        side = max(x1 - x0, y1 - y0) * float(settings.FACE_LIVENESS_CROP_SCALE)
        half = max(side * 0.5, 1.0)

        left = int(round(center_x - half))
        top = int(round(center_y - half))
        right = int(round(center_x + half))
        bottom = int(round(center_y + half))

        pad_left = max(0, -left)
        pad_top = max(0, -top)
        pad_right = max(0, right - width)
        pad_bottom = max(0, bottom - height)

        left = max(0, left)
        top = max(0, top)
        right = min(width, right)
        bottom = min(height, bottom)
        if right <= left or bottom <= top:
            return None
        crop = image[top:bottom, left:right]
        if crop.size == 0:
            return None
        if pad_left or pad_top or pad_right or pad_bottom:
            crop = self._cv2.copyMakeBorder(
                crop,
                pad_top,
                pad_bottom,
                pad_left,
                pad_right,
                self._cv2.BORDER_REFLECT_101,
            )
        return crop

    def _probabilities(self, raw: list[float]) -> list[float]:
        activation = str(settings.FACE_LIVENESS_ACTIVATION).strip().lower()
        if activation == "none":
            return [_clamp(value) for value in raw]
        if activation == "sigmoid" or len(raw) <= 1:
            return [_clamp(1.0 / (1.0 + math.exp(-value))) for value in raw]
        return _softmax(raw)

    def assess(self, image, bbox) -> LivenessResult:
        """Run the dedicated anti-spoofing classifier on a detected face crop."""
        if not self.ready:
            return LivenessResult(
                evaluated=False,
                passed=False,
                live_score=0.0,
                spoof_score=0.0,
                threshold=float(settings.FACE_LIVENESS_THRESHOLD),
                model=None,
                status="UNAVAILABLE",
                reason_code=LIVENESS_UNAVAILABLE_REASON,
                message=(
                    "The dedicated face anti-spoofing model is unavailable, so "
                    "liveness could not be evaluated."
                ),
            )

        assert self._cv2 is not None and self._np is not None
        crop = self._square_face_crop(image, bbox)
        if crop is None:
            return LivenessResult(
                evaluated=False,
                passed=False,
                live_score=0.0,
                spoof_score=0.0,
                threshold=float(settings.FACE_LIVENESS_THRESHOLD),
                model=self._model_name,
                status="ERROR",
                reason_code=LIVENESS_ERROR_REASON,
                message="The detected face region could not be cropped for liveness.",
            )

        size = int(settings.FACE_LIVENESS_INPUT_SIZE)
        resized = self._cv2.resize(crop, (size, size))
        blob = self._cv2.dnn.blobFromImage(
            resized,
            scalefactor=1.0 / 255.0,
            size=(size, size),
            mean=(0.0, 0.0, 0.0),
            swapRB=True,
        )
        try:
            with self._lock:
                self._net.setInput(blob)
                output = self._np.asarray(self._net.forward()).reshape(-1)
            probabilities = self._probabilities(
                [float(value) for value in output.tolist()]
            )
        except Exception as exc:
            return LivenessResult(
                evaluated=False,
                passed=False,
                live_score=0.0,
                spoof_score=0.0,
                threshold=float(settings.FACE_LIVENESS_THRESHOLD),
                model=self._model_name,
                status="ERROR",
                reason_code=LIVENESS_ERROR_REASON,
                message=f"The face anti-spoofing classifier failed: {exc}",
            )

        if not probabilities:
            raise BiometricProcessingError(
                "The face anti-spoofing classifier returned no scores."
            )

        live_index = min(max(int(settings.FACE_LIVENESS_LIVE_INDEX), 0), len(probabilities) - 1)
        live_score = float(probabilities[live_index])
        spoof_score = float(
            max(
                (value for index, value in enumerate(probabilities) if index != live_index),
                default=0.0,
            )
            if len(probabilities) > 1
            else 1.0 - live_score
        )
        threshold = float(settings.FACE_LIVENESS_THRESHOLD)
        passed = live_score >= threshold

        return LivenessResult(
            evaluated=True,
            passed=passed,
            live_score=live_score,
            spoof_score=spoof_score,
            threshold=threshold,
            model=self._model_name,
            status="LIVE" if passed else "SPOOF",
            reason_code=LIVENESS_VALID_REASON if passed else LIVENESS_SPOOF_REASON,
            message=(
                "Liveness check passed: the capture appears to be a live person."
                if passed
                else "Liveness check failed: a presentation attack (photo, screen, or mask) was detected."
            ),
        )


@lru_cache(maxsize=1)
def get_face_liveness_engine() -> FaceLivenessEngine:
    return FaceLivenessEngine()


def summarize_liveness(results: list[LivenessResult]) -> dict:
    """Aggregate per-frame liveness outcomes for API reporting."""
    if not results:
        return not_evaluated_result(
            LIVENESS_NOT_EVALUATED_REASON,
            "No face frame was available for a liveness check.",
        ).as_dict()

    evaluated = [result for result in results if result.evaluated]
    if not evaluated:
        first = results[0]
        return {
            **first.as_dict(),
            "samples_checked": len(results),
        }

    passed = all(result.passed for result in evaluated)
    mean_live = sum(result.live_score for result in evaluated) / len(evaluated)
    mean_spoof = sum(result.spoof_score for result in evaluated) / len(evaluated)
    model = evaluated[0].model
    status = "LIVE" if passed else "SPOOF"
    return {
        "status": status,
        "passed": passed,
        "evaluated": True,
        "live_score": round(mean_live, 4),
        "spoof_score": round(mean_spoof, 4),
        "threshold": evaluated[0].threshold,
        "anti_spoof_model": model,
        "reason_code": (
            LIVENESS_VALID_REASON if passed else LIVENESS_SPOOF_REASON
        ),
        "message": (
            "Liveness check passed: all captured frames appear to be a live person."
            if passed
            else "Liveness check failed: at least one frame appears to be a presentation attack."
        ),
        "samples_checked": len(results),
        "samples_evaluated": len(evaluated),
    }
