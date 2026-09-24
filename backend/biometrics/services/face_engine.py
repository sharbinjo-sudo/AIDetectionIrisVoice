from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
from threading import Lock

from django.conf import settings

from .exceptions import BiometricProcessingError, ModelUnavailableError


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        raise BiometricProcessingError("Face templates are missing or incompatible.")
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(
        sum(b * b for b in right)
    )
    if denominator <= 1e-12:
        raise BiometricProcessingError("A face embedding had zero length.")
    return numerator / denominator


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 1e-12:
        raise BiometricProcessingError("A face embedding had zero length.")
    return [value / norm for value in vector]


@dataclass(frozen=True)
class FaceSample:
    embedding: list[float]
    quality_score: float
    detection_confidence: float
    face_count: int
    valid_measurement: bool
    reason_code: str
    message: str


class FaceBiometricEngine:
    """InsightFace buffalo_l detector, aligner, and ArcFace embedder.

    No heuristic identity fallback is provided. The local buffalo_l SCRFD
    detector yields five landmarks; they are similarity-aligned to ArcFace's
    112x112 template before the buffalo_l recognition network is evaluated.
    """

    name = "InsightFace buffalo_l ArcFace"

    def __init__(self):
        self._detector = None
        self._recognizer = None
        self._cv2 = None
        self._np = None
        self._load_error: Exception | None = None
        self._lock = Lock()
        root = Path(settings.FACE_MODEL_ROOT)
        model_dir = root / "models" / settings.FACE_MODEL_NAME
        alternate = root / settings.FACE_MODEL_NAME
        if not model_dir.exists() and alternate.exists():
            model_dir.parent.mkdir(parents=True, exist_ok=True)
            model_dir = alternate
        self._model_dir = model_dir

        required_names = {"det_10g.onnx", "w600k_r50.onnx"}
        available = {path.name for path in model_dir.glob("*.onnx")}
        if not required_names.issubset(available):
            self._load_error = FileNotFoundError(
                "buffalo_l requires det_10g.onnx and w600k_r50.onnx in "
                f"{model_dir}"
            )
            return
        try:
            import cv2
            import numpy as np

            self._cv2 = cv2
            self._np = np
            self._detector = cv2.dnn.readNetFromONNX(
                str(model_dir / "det_10g.onnx")
            )
            self._recognizer = cv2.dnn.readNetFromONNX(
                str(model_dir / "w600k_r50.onnx")
            )
            self._detector_outputs = self._detector.getUnconnectedOutLayersNames()
        except Exception as exc:
            self._load_error = exc
            self._detector = None
            self._recognizer = None

    @property
    def ready(self) -> bool:
        return (
            self._detector is not None
            and self._recognizer is not None
            and self._cv2 is not None
        )

    def health(self) -> dict:
        return {
            "ready": self.ready,
            "name": self.name,
            "mode": "local_buffalo_l" if self.ready else "unavailable",
            "source": str(self._model_dir),
            "detail": None if self.ready else str(self._load_error),
        }

    def _ensure_ready(self) -> None:
        if not self.ready:
            raise ModelUnavailableError(
                "The face engine is not ready. Provision InsightFace buffalo_l "
                f"under {self._model_dir}. "
                f"Detail: {self._load_error}"
            )

    def _detect_faces(self, image) -> list[dict]:
        """Detect faces at useful pixel scale for wide webcam frames.

        A 1280x720 browser frame was previously reduced to 640x360 and then
        padded to 640x640. That makes a small, centered face unnecessarily
        tiny for SCRFD. For wide frames, run the same buffalo_l detector on
        overlapping square tiles and map the detections back to source pixels.
        This changes no model or embedding logic.
        """
        height, width = image.shape[:2]
        if width <= int(height * 1.25):
            return self._detect_faces_single(image)

        tile_width = min(height, width)
        positions = sorted(
            {
                0,
                max((width - tile_width) // 2, 0),
                max(width - tile_width, 0),
            }
        )
        proposals: list[dict] = []
        for x0 in positions:
            tile = image[:, x0 : x0 + tile_width]
            proposals.extend(self._detect_faces_single(tile, offset_x=x0))

        proposals.sort(key=lambda item: item["score"], reverse=True)
        kept: list[dict] = []
        for proposal in proposals:
            x0, y0, x1, y1 = proposal["bbox"]
            area = max(x1 - x0 + 1, 0) * max(y1 - y0 + 1, 0)
            suppressed = False
            for selected in kept:
                sx0, sy0, sx1, sy1 = selected["bbox"]
                intersection = max(min(x1, sx1) - max(x0, sx0) + 1, 0) * max(
                    min(y1, sy1) - max(y0, sy0) + 1,
                    0,
                )
                selected_area = max(sx1 - sx0 + 1, 0) * max(sy1 - sy0 + 1, 0)
                union = area + selected_area - intersection
                if union > 0 and intersection / union > 0.40:
                    suppressed = True
                    break
            if not suppressed:
                kept.append(proposal)
            if len(kept) >= 2:
                break
        return kept

    def _detect_faces_single(
        self,
        image,
        *,
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> list[dict]:
        assert self._cv2 is not None and self._np is not None
        source_height, source_width = image.shape[:2]
        scale = min(640.0 / source_width, 640.0 / source_height)
        resized_width = max(1, int(round(source_width * scale)))
        resized_height = max(1, int(round(source_height * scale)))
        resized = self._cv2.resize(image, (resized_width, resized_height))
        canvas = self._np.zeros((640, 640, 3), dtype=self._np.uint8)
        canvas[:resized_height, :resized_width] = resized
        blob = self._cv2.dnn.blobFromImage(
            canvas,
            scalefactor=1.0 / 128.0,
            size=(640, 640),
            mean=(127.5, 127.5, 127.5),
            swapRB=True,
        )
        with self._lock:
            self._detector.setInput(blob)
            outputs = self._detector.forward(self._detector_outputs)

        proposals: list[dict] = []
        for level, stride in enumerate((8, 16, 32)):
            scores, distances, keypoint_distances = outputs[level * 3 : level * 3 + 3]
            grid_height, grid_width = 640 // stride, 640 // stride
            centers = self._np.stack(
                self._np.mgrid[:grid_height, :grid_width][::-1],
                axis=-1,
            ).astype(self._np.float32)
            centers = (centers * stride).reshape((-1, 2))
            centers = self._np.repeat(centers, 2, axis=0)
            detection_threshold = settings.FACE_DETECTION_THRESHOLD
            if getattr(settings, "FACE_PRIMARY_CAPTURE_MODE", False):
                # The submission camera is low resolution; keep the real
                # buffalo_l detector, but permit its lower-confidence tail in
                # development. Production keeps the configured threshold.
                detection_threshold = min(detection_threshold, 0.35)
            indexes = self._np.where(scores.reshape(-1) >= detection_threshold)[0]
            for index in indexes:
                center = centers[index]
                left, top, right, bottom = distances[index] * stride
                bbox = self._np.array(
                    [
                        center[0] - left,
                        center[1] - top,
                        center[0] + right,
                        center[1] + bottom,
                    ],
                    dtype=self._np.float32,
                ) / scale
                bbox[0] += offset_x
                bbox[2] += offset_x
                bbox[1] += offset_y
                bbox[3] += offset_y
                raw_kps = keypoint_distances[index].reshape((5, 2)) * stride
                kps = self._np.empty((5, 2), dtype=self._np.float32)
                kps[:, 0] = (center[0] + raw_kps[:, 0]) / scale + offset_x
                kps[:, 1] = (center[1] + raw_kps[:, 1]) / scale + offset_y
                proposals.append(
                    {"bbox": bbox, "kps": kps, "score": float(scores[index][0])}
                )

        proposals.sort(key=lambda item: item["score"], reverse=True)
        kept: list[dict] = []
        for proposal in proposals:
            x0, y0, x1, y1 = proposal["bbox"]
            area = max(x1 - x0 + 1, 0) * max(y1 - y0 + 1, 0)
            suppressed = False
            for selected in kept:
                sx0, sy0, sx1, sy1 = selected["bbox"]
                intersection = max(min(x1, sx1) - max(x0, sx0) + 1, 0) * max(
                    min(y1, sy1) - max(y0, sy0) + 1,
                    0,
                )
                selected_area = max(sx1 - sx0 + 1, 0) * max(sy1 - sy0 + 1, 0)
                union = area + selected_area - intersection
                if union > 0 and intersection / union > 0.40:
                    suppressed = True
                    break
            if not suppressed:
                kept.append(proposal)
            if len(kept) >= 2:
                break
        return kept

    def _aligned_embedding(self, image, keypoints) -> list[float]:
        assert self._cv2 is not None and self._np is not None
        destination = self._np.asarray(
            [
                [38.2946, 51.6963],
                [73.5318, 51.5014],
                [56.0252, 71.7366],
                [41.5493, 92.3655],
                [70.7299, 92.2041],
            ],
            dtype=self._np.float32,
        )
        transform, _ = self._cv2.estimateAffinePartial2D(
            keypoints.astype(self._np.float32),
            destination,
            method=self._cv2.LMEDS,
        )
        if transform is None:
            raise BiometricProcessingError("The detected face could not be aligned.")
        aligned = self._cv2.warpAffine(
            image,
            transform,
            (112, 112),
            borderMode=self._cv2.BORDER_REFLECT_101,
        )
        blob = self._cv2.dnn.blobFromImage(
            aligned,
            scalefactor=1.0 / 127.5,
            size=(112, 112),
            mean=(127.5, 127.5, 127.5),
            swapRB=True,
        )
        with self._lock:
            self._recognizer.setInput(blob)
            vector = self._recognizer.forward().reshape(-1).astype(float).tolist()
        return _normalize(vector)

    def extract_features(self, image_path: str) -> FaceSample:
        self._ensure_ready()
        assert self._cv2 is not None
        image = self._cv2.imread(image_path)
        if image is None:
            raise BiometricProcessingError("The uploaded face image could not be read.")
        faces = self._detect_faces(image)
        if not faces:
            return FaceSample([], 0.0, 0.0, 0, False, "FACE_NOT_DETECTED", "No face was detected.")
        if len(faces) != 1:
            return FaceSample([], 0.0, 0.0, len(faces), False, "MULTIPLE_FACES", "More than one face was detected.")

        face = faces[0]
        height, width = image.shape[:2]
        x0, y0, x1, y1 = [float(value) for value in face["bbox"]]
        x0i, y0i = max(int(x0), 0), max(int(y0), 0)
        x1i, y1i = min(int(x1), width), min(int(y1), height)
        crop = image[y0i:y1i, x0i:x1i]
        if crop.size == 0:
            return FaceSample([], 0.0, float(face["score"]), 1, False, "FACE_NOT_DETECTED", "The detected face crop was empty.")

        gray = self._cv2.cvtColor(crop, self._cv2.COLOR_BGR2GRAY)
        sharpness = float(self._cv2.Laplacian(gray, self._cv2.CV_64F).var())
        brightness = float(gray.mean() / 255.0)
        face_ratio = min((x1 - x0) / max(width, 1), (y1 - y0) / max(height, 1))
        kps = face["kps"]
        eye_angle = abs(
            math.degrees(
                math.atan2(float(kps[1][1] - kps[0][1]), float(kps[1][0] - kps[0][0]))
            )
        )
        eye_mid_x = float(kps[0][0] + kps[1][0]) * 0.5
        eye_distance = max(abs(float(kps[1][0] - kps[0][0])), 1.0)
        nose_offset = abs(float(kps[2][0]) - eye_mid_x) / eye_distance

        focus_score = _clamp(sharpness / 180.0)
        brightness_score = 1.0 - _clamp(abs(brightness - 0.5) / 0.42)
        size_score = _clamp(face_ratio / 0.28)
        pose_score = _clamp(1.0 - (eye_angle / 18.0) - (nose_offset / 0.65))
        detection = _clamp(float(face["score"]))
        quality = _clamp(
            focus_score * 0.27
            + brightness_score * 0.18
            + size_score * 0.20
            + pose_score * 0.20
            + detection * 0.15
        )
        detection_threshold = settings.FACE_DETECTION_THRESHOLD
        quality_threshold = settings.FACE_QUALITY_THRESHOLD
        if getattr(settings, "FACE_PRIMARY_CAPTURE_MODE", False):
            detection_threshold = min(detection_threshold, 0.35)
            quality_threshold = min(quality_threshold, 0.45)
        valid = detection >= detection_threshold and quality >= quality_threshold
        if size_score < 0.55:
            reason, message = "FACE_TOO_SMALL", "Move closer so your face fills more of the frame."
        elif focus_score < 0.40:
            reason, message = "FACE_BLURRY", "Hold still and clean the camera lens."
        elif brightness_score < 0.35:
            reason, message = "FACE_POOR_ILLUMINATION", "Use even front lighting and avoid strong backlight."
        elif pose_score < 0.40:
            reason, message = "FACE_POSE_INVALID", "Look straight at the camera with your full face visible."
        elif not valid:
            reason, message = "FACE_QUALITY_TOO_LOW", "Face capture quality is too low. Retake the sample."
        else:
            reason, message = "FACE_VALID", "Face sample is suitable for template comparison."
        embedding = self._aligned_embedding(image, kps) if valid else []
        return FaceSample(
            embedding=embedding,
            quality_score=round(quality, 4),
            detection_confidence=round(detection, 4),
            face_count=1,
            valid_measurement=valid,
            reason_code=reason,
            message=message,
        )

    def aggregate(
        self,
        samples: list[FaceSample],
        *,
        minimum_samples: int | None = None,
    ) -> list[float]:
        required = max(1, minimum_samples or settings.MIN_FACE_SAMPLES)
        valid = [sample for sample in samples if sample.valid_measurement]
        if len(valid) < required:
            raise BiometricProcessingError(
                f"At least {required} valid face sample(s) are required."
            )
        dimension = len(valid[0].embedding)
        if any(len(sample.embedding) != dimension for sample in valid):
            raise BiometricProcessingError("Face embedding dimensions were inconsistent.")
        weights = [max(sample.quality_score, 0.05) for sample in valid]
        total = sum(weights)
        centroid = [
            sum(sample.embedding[index] * weight for sample, weight in zip(valid, weights)) / total
            for index in range(dimension)
        ]
        return _normalize(centroid)

    def compare_samples(
        self,
        samples: list[FaceSample],
        reference: list[float],
        *,
        minimum_samples: int | None = None,
    ) -> dict:
        required = max(1, minimum_samples or settings.MIN_FACE_SAMPLES)
        valid = [sample for sample in samples if sample.valid_measurement]
        if len(valid) < required:
            return {
                "face": {
                    "raw_score": 0.0,
                    "normalized_score": 0.0,
                    "quality_score": round(sum(s.quality_score for s in valid) / max(len(valid), 1), 4),
                    "detection_confidence": round(sum(s.detection_confidence for s in valid) / max(len(valid), 1), 4),
                    "valid_measurement": False,
                    "sample_count": len(valid),
                    "threshold": settings.FACE_SIMILARITY_THRESHOLD,
                    "passed": False,
                    "reason_code": "FACE_QUALITY_TOO_LOW",
                    "message": f"At least {required} valid face frame(s) are required.",
                }
            }
        probe = self.aggregate(valid, minimum_samples=required)
        raw = _cosine(probe, reference)
        score = _clamp((raw + 1.0) / 2.0)
        quality = sum(sample.quality_score for sample in valid) / len(valid)
        detection = sum(sample.detection_confidence for sample in valid) / len(valid)
        passed = score >= settings.FACE_SIMILARITY_THRESHOLD
        return {
            "face": {
                "raw_score": round(raw, 4),
                "normalized_score": round(score, 4),
                "similarity_score": round(score, 4),
                "quality_score": round(quality, 4),
                "quality_threshold": settings.FACE_QUALITY_THRESHOLD,
                "detection_confidence": round(detection, 4),
                "valid_measurement": True,
                "sample_count": len(valid),
                "threshold": settings.FACE_SIMILARITY_THRESHOLD,
                "passed": passed,
                "reason_code": "FACE_MATCH" if passed else "FACE_MISMATCH",
                "message": "Face matched the enrolled template." if passed else "Face did not match the enrolled template.",
            }
        }


@lru_cache(maxsize=1)
def get_face_engine() -> FaceBiometricEngine:
    return FaceBiometricEngine()
