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
from datetime import datetime, timezone
from functools import lru_cache
import logging
import math
from pathlib import Path
from threading import Lock

from django.conf import settings

from .exceptions import BiometricProcessingError, ModelUnavailableError
from .model_assets import ensure_remote_asset

logger = logging.getLogger(__name__)

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

    @staticmethod
    def _reference_clamped_crop_bounds(
        image_shape: tuple, bbox_xywh: list[float], scale: float
    ) -> tuple[int, int, int, int, float]:
        """Reference (yakhyo/face-anti-spoofing onnx_inference.py) crop bounds.

        The scale is limited so the squared-up face box always fits inside the
        source image; the resulting box is clamped to the image bounds instead
        of being reflect-padded. Returns (x1, y1, x2, y2) inclusive-ish ints
        matching the reference slicing convention ``image[y1:y2+1, x1:x2+1]``.
        """
        src_h, src_w = image_shape[:2]
        x, y, box_w, box_h = bbox_xywh
        clamped_scale = min(
            (src_h - 1) / box_h,
            (src_w - 1) / box_w,
            scale,
        )
        new_w = box_w * clamped_scale
        new_h = box_h * clamped_scale
        center_x = x + box_w / 2
        center_y = y + box_h / 2
        x1 = max(0, int(center_x - new_w / 2))
        y1 = max(0, int(center_y - new_h / 2))
        x2 = min(src_w - 1, int(center_x + new_w / 2))
        y2 = min(src_h - 1, int(center_y + new_h / 2))
        return x1, y1, x2, y2, clamped_scale

    def _square_face_crop(self, image, bbox):
        """Crop the detected face for MiniFASNet, reference-style.

        Converts [x1,y1,x2,y2] to [x,y,w,h], limits the crop scale so the
        squared-up box stays inside the source image (never reflect-pads), and
        returns the clamped crop. Callers resize it to the model input size.
        """
        height, width = image.shape[:2]
        x0, y0, x1, y1 = [float(value) for value in bbox]
        bbox_xywh = [x0, y0, x1 - x0, y1 - y0]
        scale = float(settings.FACE_LIVENESS_CROP_SCALE)
        if bbox_xywh[2] <= 0 or bbox_xywh[3] <= 0:
            return None
        left, top, right, bottom, _used_scale = self._reference_clamped_crop_bounds(
            image.shape, bbox_xywh, scale
        )
        if right <= left or bottom <= top:
            return None
        crop = image[top : bottom + 1, left : right + 1]
        if crop.size == 0:
            return None
        return crop

    def _save_debug_crop(self, crop, resized) -> str | None:
        """Persist the exact classifier input crop for manual inspection.

        Enabled with FACE_LIVENESS_DEBUG_SAVE_CROP=True. Diagnostics only:
        failures here must never change an assessment outcome.
        """
        if not getattr(settings, "FACE_LIVENESS_DEBUG_SAVE_CROP", False):
            return None
        try:
            directory = Path(settings.MEDIA_ROOT) / "liveness_debug"
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            crop_path = directory / f"liveness_crop_{stamp}.jpg"
            resized_path = directory / f"liveness_crop_{stamp}_80x80.jpg"
            self._cv2.imwrite(str(crop_path), crop)
            self._cv2.imwrite(str(resized_path), resized)
            logger.info("face liveness debug crop saved: %s", crop_path)
            return str(crop_path)
        except Exception as exc:  # pragma: no cover - diagnostics only
            logger.warning("Could not save liveness debug crop: %s", exc)
            return None

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
        # Upstream preprocessing: the clamped crop is resized directly to the
        # model input (80x80). BGR in, raw float32 0-255 pixels, NCHW; swapRB
        # stays False. No alignment warp.
        resized = self._cv2.resize(crop, (size, size))
        saved_crop_path = self._save_debug_crop(crop, resized)
        # Convention decision (NOT chosen because it produces PASS).
        #
        # Basis: the A/B/C diagnostic (backend/diag_liveness.py) on a genuine
        # webcam frame, plus the upstream implementation
        # (yakhyo/face-anti-spoofing onnx_inference.py), which feeds BGR,
        # float32 RAW 0-255 pixels, NCHW, a 2.7 crop, and treats class
        # index 1 as Real.
        #
        # The Hugging Face model card
        # (garciafido/minifasnet-v2-anti-spoofing-onnx) documents /255 with
        # class 0 = live, but the actual checkpoint behaviour matches the
        # upstream Silent-Face/MiniFASNet inference convention much more
        # closely: on the SAME real webcam face and crop, /255 produced
        # softmax [0.0004, 0.0061, 0.9935] (argmax 2), while raw 0-255
        # produced [0.0071, 0.9799, 0.0131] (argmax 1), and the byte-exact
        # upstream-replica pipeline agreed ([0.0112, 0.9413, 0.0475]).
        # OpenCV images are already BGR, so swapRB must stay False; NCHW
        # comes from blobFromImage.
        blob = self._cv2.dnn.blobFromImage(
            resized,
            scalefactor=1.0,
            size=(size, size),
            mean=(0.0, 0.0, 0.0),
            swapRB=False,
        )
        try:
            with self._lock:
                self._net.setInput(blob)
                output = self._np.asarray(self._net.forward()).reshape(-1)
            raw_values = [float(value) for value in output.tolist()]
            probabilities = self._probabilities(raw_values)
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
        predicted_class = max(range(len(probabilities)), key=lambda index: probabilities[index])
        spoof_score = float(
            max(
                (value for index, value in enumerate(probabilities) if index != live_index),
                default=0.0,
            )
            if len(probabilities) > 1
            else 1.0 - live_score
        )

        # Score diagnostics on every assessment: raw logits, softmax,
        # predicted class, live and spoof probability. Kept at INFO so
        # production captures can be audited against the A/B/C diagnostic
        # evidence that fixed the preprocessing/class conventions.
        logger.info(
            "face liveness diagnostic: crop=%dx%d resized=%dx%d input_minmax=%.4f/%.4f "
            "raw_logits=%s softmax=%s predicted_class=%d live_index=%d "
            "live_prob=%.4f spoof_prob=%.4f debug_crop=%s",
            crop.shape[1],
            crop.shape[0],
            size,
            size,
            float(resized.min()),
            float(resized.max()),
            [round(value, 4) for value in raw_values],
            [round(value, 4) for value in probabilities],
            predicted_class,
            live_index,
            live_score,
            spoof_score,
            saved_crop_path,
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
    """Aggregate per-frame liveness outcomes for API reporting.

    Enrollment captures several frames, and a single noisy frame (motion
    blur, a half-blink, partial occlusion) must not reject an otherwise live
    capture. The aggregate verdict combines three signals over the evaluated
    frames:

    1. mean live probability across frames,
    2. a majority of frames classified LIVE at the configured threshold,
    3. aggregate spoof evidence (mean spoof score) at the same threshold.

    Verdict rules:
    - SPOOF when a majority of frames are spoof or mean spoof evidence is
      itself above the threshold (overwhelming spoof evidence).
    - LIVE only when the mean live score passes, a majority (not merely
      some) of frames are LIVE, and aggregate spoof evidence stays below
      the threshold.
    - An evenly split vote without spoof evidence is treated as ambiguous
      and rejected: an ambiguous capture must not pass.
    """
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

    total = len(evaluated)
    live_votes = sum(1 for result in evaluated if result.passed)
    spoof_votes = total - live_votes
    mean_live = sum(result.live_score for result in evaluated) / total
    mean_spoof = sum(result.spoof_score for result in evaluated) / total
    majority = total // 2 + 1
    threshold = evaluated[0].threshold

    majority_live = live_votes >= majority
    majority_spoof = spoof_votes >= majority
    spoof_evidence = mean_spoof >= threshold

    if majority_spoof or spoof_evidence:
        # Aggregate evidence indicates a presentation attack; a handful of
        # borderline frames must not mask it.
        passed = False
    else:
        # Majority LIVE + passing mean live score => live.
        passed = majority_live and mean_live >= threshold

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
            "Liveness check passed: the captured frames collectively appear to "
            "be a live person."
            if passed
            else "Liveness check failed: the captured frames collectively appear "
            "to be a presentation attack."
        ),
        "samples_checked": len(results),
        "samples_evaluated": len(evaluated),
        "live_votes": live_votes,
        "spoof_votes": spoof_votes,
    }
