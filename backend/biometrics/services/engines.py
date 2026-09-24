from __future__ import annotations

import atexit
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
import struct
from threading import Lock
import wave

from django.conf import settings

from .exceptions import BiometricProcessingError, ModelUnavailableError
from .model_assets import ensure_remote_asset


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        raise BiometricProcessingError(
            "Stored biometric templates are missing or incompatible."
        )
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        raise BiometricProcessingError("Encountered a zero-length biometric embedding.")
    return numerator / (left_norm * right_norm)


def _normalize_vector(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 1e-12:
        raise BiometricProcessingError("Encountered a zero-length biometric embedding.")
    return [value / norm for value in values]


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / float(len(values))


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((value - avg) ** 2 for value in values) / float(len(values))
    return math.sqrt(variance)


def _histogram(values: list[float], bins: int, *, value_min: float, value_max: float) -> list[float]:
    if bins <= 0:
        return []
    counts = [0.0 for _ in range(bins)]
    span = max(value_max - value_min, 1e-6)
    for value in values:
        normalized = (value - value_min) / span
        index = min(bins - 1, max(0, int(normalized * bins)))
        counts[index] += 1.0
    total = sum(counts) or 1.0
    return [count / total for count in counts]


def _downsample(values: list[float], target_size: int) -> list[float]:
    if not values or target_size <= 0:
        return [0.0 for _ in range(max(target_size, 0))]
    if len(values) == target_size:
        return list(values)
    result: list[float] = []
    for index in range(target_size):
        start = int(index * len(values) / target_size)
        end = int((index + 1) * len(values) / target_size)
        bucket = values[start:end] or [values[min(start, len(values) - 1)]]
        result.append(_mean(bucket))
    return result


@dataclass
class VoiceSample:
    duration_seconds: float
    quality_score: float
    speech_activity_score: float
    rms_level: float
    peak_level: float
    embedding: list[float]
    segment_count: int = 1


@dataclass
class IrisSample:
    iris_detected: bool
    quality_score: float
    embedding: list[float]
    detection_confidence: float = 0.0


@dataclass
class IrisCandidate:
    center_x: float
    center_y: float
    radius: float
    quality_score: float
    embedding: list[float]
    grayscale: list[float]


class VoiceBiometricEngine:
    name = "SpeechBrain ECAPA"

    def __init__(self):
        self._load_error = None
        self._classifier = None
        self._torch = None
        self._librosa = None
        self._mode = "heuristic"
        self._source = "heuristic"

        try:
            import librosa
            import torch
            from speechbrain.inference.speaker import EncoderClassifier
            from speechbrain.utils.fetching import FetchConfig, LocalStrategy
        except Exception as exc:
            self._load_error = exc
            return

        self._librosa = librosa
        self._torch = torch
        cache_dir = Path(settings.VOICE_MODEL_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)
        local_voice_dir = Path(settings.LOCAL_VOICE_MODEL_DIR)
        sources: list[tuple[str, str, str]] = []
        if (local_voice_dir / "hyperparams.yaml").exists():
            local_voice_dir.mkdir(parents=True, exist_ok=True)
            sources.append(("local_pretrained", str(local_voice_dir), str(local_voice_dir)))
        if not settings.BIOMETRIC_OFFLINE_MODE:
            sources.append(("pretrained", settings.VOICE_MODEL_SOURCE, str(cache_dir)))

        load_errors: list[str] = []
        for mode, source, savedir in sources:
            try:
                self._classifier = EncoderClassifier.from_hparams(
                    source=source,
                    savedir=savedir,
                    run_opts={"device": "cpu"},
                    local_strategy=LocalStrategy.COPY,
                    fetch_config=FetchConfig(
                        allow_network=not settings.BIOMETRIC_OFFLINE_MODE,
                        allow_updates=False,
                    ),
                )
                self._mode = mode
                self._source = source
                self._load_error = None
                break
            except Exception as exc:
                load_errors.append(f"{mode}: {exc}")
                self._load_error = exc
        if load_errors and self._classifier is None:
            self._load_error = RuntimeError("; ".join(load_errors))

    @property
    def ready(self) -> bool:
        return self._mode in {"pretrained", "local_pretrained"}

    @property
    def mode(self) -> str:
        return self._mode

    def health(self) -> dict:
        detail = None
        if self._mode not in {"pretrained", "local_pretrained"} and self._load_error is not None:
            detail = f"Using heuristic voice fallback. Local model load detail: {self._load_error}"
        return {
            "ready": self.ready,
            "name": self.name if self._mode in {"pretrained", "local_pretrained"} else "Heuristic Voice Analyzer",
            "mode": self._mode,
            "source": self._source,
            "cache_dir": str(settings.VOICE_MODEL_CACHE_DIR),
            "detail": detail,
        }

    def _ensure_ready(self) -> None:
        if self.ready or settings.DEVELOPMENT_THRESHOLDS:
            return
        raise ModelUnavailableError(
            "The local voice model is unavailable. Provision the local "
            "SpeechBrain files and restart the backend."
        )

    def _extract_fallback_wav(self, audio_path: str) -> tuple[list[float], int]:
        try:
            with wave.open(audio_path, "rb") as handle:
                channels = handle.getnchannels()
                sample_width = handle.getsampwidth()
                sample_rate = handle.getframerate()
                frame_count = handle.getnframes()
                raw_frames = handle.readframes(frame_count)
        except Exception as exc:
            raise BiometricProcessingError(
                "The uploaded voice recording could not be decoded."
            ) from exc

        if frame_count <= 0 or not raw_frames:
            raise BiometricProcessingError("The uploaded voice recording was empty.")

        if sample_width == 1:
            unpacked = struct.unpack(f"<{len(raw_frames)}B", raw_frames)
            samples = [float(value - 128) / 128.0 for value in unpacked]
        elif sample_width == 2:
            unpacked = struct.unpack(f"<{len(raw_frames) // 2}h", raw_frames)
            samples = [float(value) / 32768.0 for value in unpacked]
        elif sample_width == 4:
            unpacked = struct.unpack(f"<{len(raw_frames) // 4}i", raw_frames)
            samples = [float(value) / 2147483648.0 for value in unpacked]
        else:
            raise BiometricProcessingError("Unsupported WAV sample width.")

        if channels > 1:
            mono_samples = []
            for index in range(0, len(samples), channels):
                frame = samples[index : index + channels]
                mono_samples.append(_mean(frame))
            samples = mono_samples

        return samples, sample_rate

    def _extract_fallback_features(self, audio_path: str) -> VoiceSample:
        signal, sample_rate = self._extract_fallback_wav(audio_path)
        duration_seconds = float(len(signal)) / float(sample_rate or 1)
        rms_energy = math.sqrt(_mean([sample * sample for sample in signal]))
        peak_level = max((abs(sample) for sample in signal), default=0.0)

        frame_size = max(int(sample_rate * 0.04), 160)
        active_frames = 0
        total_frames = 0
        for start in range(0, len(signal), frame_size):
            frame = signal[start : start + frame_size]
            if not frame:
                continue
            total_frames += 1
            frame_energy = _mean([abs(sample) for sample in frame])
            if frame_energy >= 0.025:
                active_frames += 1
        speech_activity_score = (
            float(active_frames) / float(total_frames) if total_frames else 0.0
        )

        duration_score = _clamp(duration_seconds / max(settings.VOICE_MIN_SECONDS, 0.1))
        energy_score = _clamp(rms_energy / 0.08)
        activity_score = _clamp(
            speech_activity_score / max(settings.VOICE_ACTIVITY_THRESHOLD, 0.05)
        )
        quality_score = _round4(
            (duration_score * 0.45) + (energy_score * 0.20) + (activity_score * 0.35)
        ) or 0.0

        absolute_samples = [abs(sample) for sample in signal]
        amplitude_histogram = _histogram(
            absolute_samples,
            12,
            value_min=0.0,
            value_max=1.0,
        )
        zero_crossings = 0.0
        if len(signal) > 1:
            zero_crossings = sum(
                1
                for left, right in zip(signal, signal[1:])
                if (left <= 0 < right) or (left >= 0 > right)
            ) / float(len(signal) - 1)
        embedding = amplitude_histogram + [
            _clamp(zero_crossings),
            _clamp(rms_energy / 0.25),
            _clamp(peak_level),
            _clamp(duration_seconds / max(settings.VOICE_MAX_SECONDS, 1.0)),
            _clamp(speech_activity_score),
        ]

        return VoiceSample(
            duration_seconds=_round4(duration_seconds) or 0.0,
            quality_score=quality_score,
            speech_activity_score=_round4(speech_activity_score) or 0.0,
            rms_level=_round4(rms_energy) or 0.0,
            peak_level=_round4(peak_level) or 0.0,
            embedding=embedding,
            segment_count=max(
                1,
                int(duration_seconds // max(settings.VOICE_MIN_SECONDS, 0.1)),
            ),
        )

    def extract_features(self, audio_path: str) -> VoiceSample:
        self._ensure_ready()
        if self._mode not in {"pretrained", "local_pretrained"}:
            return self._extract_fallback_features(audio_path)

        assert self._torch is not None

        try:
            signal_values, sample_rate = self._extract_fallback_wav(audio_path)
        except BiometricProcessingError as exc:
            raise BiometricProcessingError(
                "The uploaded voice recording could not be decoded."
            ) from exc

        if not signal_values:
            raise BiometricProcessingError("The uploaded voice recording was empty.")

        duration_seconds = float(len(signal_values)) / float(sample_rate or 1)
        target_sample_rate = int(settings.VOICE_SAMPLE_RATE)
        if sample_rate != target_sample_rate:
            try:
                import numpy as np

                signal_values = self._librosa.resample(
                    y=np.asarray(signal_values, dtype=np.float32),
                    orig_sr=sample_rate,
                    target_sr=target_sample_rate,
                ).astype(float).tolist()
                sample_rate = target_sample_rate
            except Exception as exc:
                raise BiometricProcessingError(
                    "The voice recording sample rate could not be normalized."
                ) from exc
        rms_energy = math.sqrt(_mean([sample * sample for sample in signal_values]))
        peak_level = max((abs(sample) for sample in signal_values), default=0.0)

        frame_length = min(2048, max(256, int(sample_rate * 0.08)))
        hop_length = max(128, frame_length // 2)
        frame_scores: list[float] = []
        for start in range(0, len(signal_values), hop_length):
            frame = signal_values[start : start + frame_length]
            if not frame:
                continue
            frame_scores.append(math.sqrt(_mean([sample * sample for sample in frame])))
        if not frame_scores:
            speech_activity_score = 0.0
        else:
            active_frames = sum(1 for score in frame_scores if score >= 0.018)
            speech_activity_score = float(active_frames) / float(len(frame_scores))

        duration_score = _clamp(duration_seconds / max(settings.VOICE_MIN_SECONDS, 0.1))
        energy_score = _clamp(rms_energy / 0.08)
        activity_score = _clamp(
            speech_activity_score / max(settings.VOICE_ACTIVITY_THRESHOLD, 0.05)
        )
        quality_score = _round4(
            (duration_score * 0.45) + (energy_score * 0.20) + (activity_score * 0.35)
        ) or 0.0

        segment_size = max(
            int(sample_rate * settings.VOICE_MIN_SECONDS),
            1,
        )
        segments = [
            signal_values[start : start + segment_size]
            for start in range(0, len(signal_values), segment_size)
            if len(signal_values[start : start + segment_size]) >= segment_size
        ]
        if not segments:
            segments = [signal_values]
        try:
            with self._torch.no_grad():
                embeddings = []
                for segment in segments:
                    tensor = self._torch.tensor(
                        segment,
                        dtype=self._torch.float32,
                    ).unsqueeze(0)
                    encoded = self._classifier.encode_batch(tensor)
                    vector = encoded.squeeze().cpu().numpy().astype(float)
                    norm = math.sqrt(float((vector * vector).sum()))
                    embeddings.append(vector / max(norm, 1e-12))
            averaged = sum(embeddings) / float(len(embeddings))
            averaged /= max(float((averaged * averaged).sum()) ** 0.5, 1e-12)
            embedding = averaged.astype(float).tolist()
        except Exception as exc:
            raise BiometricProcessingError(
                "The pretrained voice model could not generate an embedding for this sample."
            ) from exc

        return VoiceSample(
            duration_seconds=_round4(duration_seconds) or 0.0,
            quality_score=quality_score,
            speech_activity_score=_round4(speech_activity_score) or 0.0,
            rms_level=_round4(rms_energy) or 0.0,
            peak_level=_round4(peak_level) or 0.0,
            embedding=embedding,
            segment_count=len(segments),
        )

    def aggregate_samples(self, samples: list[VoiceSample]) -> list[float]:
        """Build one speaker template from multiple quality-checked captures."""
        if not samples:
            raise BiometricProcessingError(
                "At least one usable voice sample is required to build a template."
            )
        dimensions = {len(sample.embedding) for sample in samples}
        if len(dimensions) != 1 or not next(iter(dimensions), 0):
            raise BiometricProcessingError(
                "Voice samples produced incompatible speaker embeddings."
            )
        weights = [max(float(sample.quality_score), 0.05) for sample in samples]
        total_weight = sum(weights)
        combined = [
            sum(sample.embedding[index] * weight for sample, weight in zip(samples, weights))
            / total_weight
            for index in range(len(samples[0].embedding))
        ]
        return _normalize_vector(combined)

    def compare(self, audio_path: str, reference_embedding: list[float]) -> dict:
        sample = self.extract_features(audio_path)
        raw_score = _cosine_similarity(sample.embedding, reference_embedding)
        normalized_score = _clamp((raw_score + 1.0) / 2.0)
        quality_ok = sample.quality_score >= settings.VOICE_QUALITY_THRESHOLD
        activity_ok = sample.speech_activity_score >= settings.VOICE_ACTIVITY_THRESHOLD
        segments_ok = sample.segment_count >= settings.MIN_VOICE_SEGMENTS
        match_ok = normalized_score >= settings.VOICE_SIMILARITY_THRESHOLD
        passed = quality_ok and activity_ok and segments_ok and match_ok

        if sample.duration_seconds < settings.VOICE_MIN_SECONDS:
            message = "The recording was too quiet or too short. Speak clearly and try again."
        elif not segments_ok:
            message = (
                f"Record at least {settings.MIN_VOICE_SEGMENTS} clear voice segments."
            )
        elif not activity_ok:
            message = "No clear spoken microphone activity was detected. Speak clearly into the mic and try again."
        elif not quality_ok:
            message = "The recording was too quiet or too short. Speak clearly and try again."
        elif not match_ok:
            message = "Voice did not match the reference template."
        else:
            message = "Microphone activity, voice quality, and speaker comparison passed."

        return {
            "voice": {
                "duration_seconds": sample.duration_seconds,
                "quality_score": sample.quality_score,
                "speech_detected": activity_ok,
                "speech_activity_score": sample.speech_activity_score,
                "rms_level": sample.rms_level,
                "peak_level": sample.peak_level,
                "segment_count": sample.segment_count,
                "raw_score": _round4(raw_score),
                "normalized_score": _round4(normalized_score),
                "threshold": settings.VOICE_SIMILARITY_THRESHOLD,
                "passed": passed,
                "message": message,
            },
            "message": message,
        }


class IrisBiometricEngine:
    name = "Local Iris ONNX Segmenter"

    # MediaPipe Face Mesh contour landmarks only. Iris landmarks (468-477)
    # are intentionally excluded: MediaPipe localizes the eye ROIs, while the
    # Worldcoin ONNX model remains the sole iris detector/segmenter.
    _LEFT_EYE_CONTOUR = (
        362, 382, 381, 380, 374, 373, 390, 249,
        263, 466, 388, 387, 386, 385, 384, 398,
    )
    _RIGHT_EYE_CONTOUR = (
        33, 7, 163, 144, 145, 153, 154, 155,
        133, 173, 157, 158, 159, 160, 161, 246,
    )

    def __init__(self):
        self._load_error = None
        self._cv2 = None
        self._mp = None
        self._np = None
        self._Image = None
        self._landmarker = None
        self._onnx_net = None
        self._onnx_inference_lock = Lock()
        self._landmarker_inference_lock = Lock()
        self._mode = "heuristic"
        self._source = "heuristic"
        self._model_path = Path(settings.IRIS_MODEL_PATH)
        self._onnx_model_path = Path(settings.LOCAL_IRIS_ONNX_MODEL_PATH)

        try:
            from PIL import Image
        except Exception as exc:
            self._load_error = exc
            return

        self._Image = Image

        try:
            import cv2
            import numpy as np
            self._cv2 = cv2
            self._np = np
            if self._onnx_model_path.exists():
                self._onnx_net = cv2.dnn.readNetFromONNX(str(self._onnx_model_path))
                self._mode = "local_onnx"
                self._source = str(self._onnx_model_path)
                self._load_error = None
        except Exception as exc:
            self._load_error = exc

        try:
            if self._cv2 is None or self._np is None:
                raise RuntimeError("OpenCV and NumPy are required for eye ROI localization.")
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
        except Exception as exc:
            self._load_error = exc
            return

        self._mp = mp

        try:
            if self._model_path.exists():
                model_path = self._model_path
            elif settings.BIOMETRIC_OFFLINE_MODE:
                raise ModelUnavailableError(
                    "The local MediaPipe face-landmarker asset is missing. "
                    f"Expected it at {self._model_path}."
                )
            else:
                model_path = ensure_remote_asset(
                    destination=self._model_path,
                    description="face-landmarker model",
                    urls=[settings.IRIS_MODEL_URL],
                )
            options = vision.FaceLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=str(model_path)),
                running_mode=vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.35,
                min_face_presence_confidence=0.35,
                min_tracking_confidence=0.35,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )
            self._landmarker = vision.FaceLandmarker.create_from_options(options)
            if self._onnx_net is None:
                self._mode = "pretrained"
                self._source = settings.IRIS_MODEL_URL
            self._load_error = None
        except Exception as exc:
            self._load_error = exc

    @property
    def ready(self) -> bool:
        return (
            self._mode == "local_onnx"
            and self._Image is not None
            and self._cv2 is not None
            and self._np is not None
            and getattr(self, "_landmarker", None) is not None
            and getattr(self, "_onnx_net", None) is not None
        )

    @property
    def mode(self) -> str:
        return self._mode

    def health(self) -> dict:
        detail = None
        if self._mode == "heuristic" and self._load_error is not None:
            detail = (
                "Iris engine unavailable; no fallback detector is permitted. "
                f"Model load detail: {self._load_error}"
            )
        model_name = "Local Iris ONNX Segmenter"
        return {
            "ready": self.ready,
            "name": model_name,
            "mode": self._mode,
            "source": self._source,
            "cached_asset": str(self._onnx_model_path if self._mode == "local_onnx" else self._model_path),
            "detail": detail,
        }

    def _ensure_ready(self):
        if not self.ready:
            raise ModelUnavailableError(
                "The iris verification engine is not ready. The Worldcoin ONNX "
                "segmenter, MediaPipe eye-ROI asset, OpenCV, NumPy, and Pillow "
                "must all be available locally."
            )

    def close(self) -> None:
        """Release native MediaPipe resources before interpreter teardown."""
        landmarker = getattr(self, "_landmarker", None)
        self._landmarker = None
        if landmarker is not None:
            try:
                landmarker.close()
            except Exception:
                # Native resources may already have been reclaimed while the
                # process is shutting down.
                pass

    def _read_image(self, image_path: str):
        self._ensure_ready()
        assert self._Image is not None
        try:
            return self._Image.open(image_path).convert("L")
        except Exception as exc:
            raise BiometricProcessingError("The uploaded iris image could not be read.") from exc

    def _crop_central_square(self, image):
        width, height = image.size
        size = int(min(width, height) * 0.55)
        size = max(size, 96)
        size = min(size, min(width, height))
        x0 = max((width - size) // 2, 0)
        y0 = max((height - size) // 2, 0)
        return image.crop((x0, y0, x0 + size, y0 + size))

    def _quality_score_from_pixels(self, pixels: list[float], width: int, height: int) -> float:
        if not pixels or width <= 1 or height <= 1:
            return 0.0

        brightness = _mean(pixels) / 255.0
        contrast = _stdev(pixels) / 64.0

        horizontal_edges: list[float] = []
        vertical_edges: list[float] = []
        for row in range(height):
            row_offset = row * width
            for col in range(width - 1):
                left = pixels[row_offset + col]
                right = pixels[row_offset + col + 1]
                horizontal_edges.append(abs(right - left))
        for row in range(height - 1):
            row_offset = row * width
            next_row_offset = (row + 1) * width
            for col in range(width):
                top = pixels[row_offset + col]
                bottom = pixels[next_row_offset + col]
                vertical_edges.append(abs(bottom - top))

        focus = (_mean(horizontal_edges) + _mean(vertical_edges)) / 2.0
        focus_score = _clamp(focus / 22.0)
        brightness_score = 1.0 - min(abs(brightness - 0.5) / 0.5, 1.0)
        contrast_score = _clamp(contrast)
        size_score = _clamp(min(width, height) / 180.0)

        return _round4(
            (focus_score * 0.35)
            + (brightness_score * 0.20)
            + (contrast_score * 0.20)
            + (size_score * 0.25)
        ) or 0.0

    def _build_embedding_from_pixels(self, pixels: list[float], width: int, height: int) -> list[float]:
        image_vector = _downsample([value / 255.0 for value in pixels], 64)
        histogram = _histogram(pixels, 16, value_min=0.0, value_max=255.0)
        geometry = [
            _clamp(width / 512.0),
            _clamp(height / 512.0),
            _clamp(_stdev(pixels) / 80.0),
        ]
        return image_vector + histogram + geometry

    def _extract_fallback_candidate(self, image) -> IrisCandidate:
        crop = self._crop_central_square(image)
        resized = crop.resize((96, 96))
        pixels = [float(value) for value in resized.getdata()]
        quality_score = self._quality_score_from_pixels(pixels, 96, 96)
        embedding = self._build_embedding_from_pixels(pixels, 96, 96)
        return IrisCandidate(
            center_x=0.5,
            center_y=0.5,
            radius=48.0,
            quality_score=quality_score,
            embedding=embedding,
            grayscale=pixels,
        )

    def _detect_landmarks(self, image) -> list[object]:
        assert self._cv2 is not None
        assert self._mp is not None

        rgb_image = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=rgb_image,
        )
        if self._landmarker is None:
            return []
        with self._landmarker_inference_lock:
            result = self._landmarker.detect(mp_image)
        if not result.face_landmarks:
            return []
        return result.face_landmarks[0]

    def _eye_rois_from_face_landmarks(self, image, landmarks: list[object]) -> list[dict]:
        """Build padded eye crops using only non-iris face contour landmarks."""
        assert self._np is not None
        height, width = image.shape[:2]
        rois: list[dict] = []
        for eye_side, indices in (
            ("LEFT", self._LEFT_EYE_CONTOUR),
            ("RIGHT", self._RIGHT_EYE_CONTOUR),
        ):
            if not landmarks or max(indices) >= len(landmarks):
                continue
            points = self._np.array(
                [
                    [landmarks[index].x * width, landmarks[index].y * height]
                    for index in indices
                ],
                dtype=self._np.float32,
            )
            min_x, min_y = points.min(axis=0)
            max_x, max_y = points.max(axis=0)
            eye_width = float(max_x - min_x)
            eye_height = float(max_y - min_y)
            if eye_width < 8.0 or eye_height < 3.0:
                continue

            center_x = float((min_x + max_x) * 0.5)
            center_y = float((min_y + max_y) * 0.5)
            # Preserve eyelid/sclera context while enlarging the iris
            # substantially. Match the live ONNX tensor aspect ratio exactly,
            # avoiding a preprocessing stretch that would skew the ellipse.
            roi_width = max(eye_width * 1.75, eye_height * 4.2, 48.0)
            roi_height = roi_width * (
                float(settings.IRIS_TRACKING_INPUT_HEIGHT)
                / float(settings.IRIS_TRACKING_INPUT_WIDTH)
            )
            x0 = max(int(round(center_x - roi_width * 0.5)), 0)
            x1 = min(int(round(center_x + roi_width * 0.5)), width)
            y0 = max(int(round(center_y - roi_height * 0.5)), 0)
            y1 = min(int(round(center_y + roi_height * 0.5)), height)
            if x1 - x0 < 24 or y1 - y0 < 18:
                continue
            rois.append(
                {
                    "eye_side": eye_side,
                    "x": x0,
                    "y": y0,
                    "width": x1 - x0,
                    "height": y1 - y0,
                    "crop": image[y0:y1, x0:x1],
                }
            )
        return rois

    def _group_iris_landmarks(self, landmarks: list[object]) -> list[list[object]]:
        if len(landmarks) < 478:
            return []
        iris_points = list(landmarks[-10:])
        iris_points.sort(key=lambda point: point.x)
        return [iris_points[:5], iris_points[5:]]

    def _crop_from_group(self, image, group: list[object]):
        assert self._np is not None

        height, width = image.shape[:2]
        points = self._np.array(
            [[point.x * width, point.y * height] for point in group],
            dtype=self._np.float32,
        )
        center = points.mean(axis=0)
        distances = self._np.linalg.norm(points - center, axis=1)
        radius = float(max(distances.mean(), 4.0))
        pad = max(int(radius * 5.5), 24)

        x0 = max(int(center[0]) - pad, 0)
        y0 = max(int(center[1]) - pad, 0)
        x1 = min(int(center[0]) + pad, width)
        y1 = min(int(center[1]) + pad, height)
        if x1 <= x0 or y1 <= y0:
            return None
        return {
            "center_x": float(center[0]) / float(width),
            "center_y": float(center[1]) / float(height),
            "radius": radius,
            "crop": image[y0:y1, x0:x1],
            "image_min_side": float(min(height, width)),
        }

    def _quality_score_pretrained(self, crop, radius: float, image_min_side: float) -> float:
        assert self._cv2 is not None
        assert self._np is not None

        if crop.size == 0:
            return 0.0

        gray = self._cv2.cvtColor(crop, self._cv2.COLOR_BGR2GRAY)
        focus = float(self._cv2.Laplacian(gray, self._cv2.CV_64F).var())
        brightness = float(self._np.mean(gray) / 255.0)
        contrast = float(self._np.std(gray) / 64.0)
        radius_ratio = radius / max(image_min_side, 1.0)

        focus_score = _clamp(focus / 180.0)
        brightness_score = 1.0 - min(abs(brightness - 0.5) / 0.5, 1.0)
        contrast_score = _clamp(contrast)
        size_score = _clamp(radius_ratio / 0.045)

        return _round4(
            (focus_score * 0.35)
            + (brightness_score * 0.20)
            + (contrast_score * 0.20)
            + (size_score * 0.25)
        ) or 0.0

    def _build_embedding_pretrained(self, crop, radius: float, image_min_side: float) -> list[float]:
        assert self._cv2 is not None
        assert self._np is not None

        gray = self._cv2.cvtColor(crop, self._cv2.COLOR_BGR2GRAY)
        resized = self._cv2.resize(gray, (16, 16), interpolation=self._cv2.INTER_AREA)
        histogram = self._cv2.calcHist([gray], [0], None, [16], [0, 256]).flatten()
        histogram_sum = float(histogram.sum()) or 1.0
        resized_vector = resized.astype(self._np.float32).flatten() / 255.0
        histogram_vector = histogram.astype(self._np.float32) / histogram_sum
        geometry_vector = self._np.array(
            [
                _clamp(radius / max(image_min_side, 1.0)),
                float(gray.mean()) / 255.0,
                _clamp(float(gray.std()) / 64.0),
            ],
            dtype=self._np.float32,
        )
        embedding = self._np.concatenate(
            [resized_vector, histogram_vector, geometry_vector]
        )
        return embedding.astype(float).tolist()

    def _build_segmented_iris_embedding(self, crop, geometry: dict, roi: dict) -> list[float]:
        """Normalize the ONNX-confirmed iris region into a comparable pattern.

        The segmentation network remains the only iris detector.  This is a
        deterministic texture descriptor (not another AI model): rotate the
        fitted ellipse, crop it, normalize illumination, and z-score pixels.
        """
        assert self._cv2 is not None
        assert self._np is not None
        center = (
            float(geometry["center_x"]) - float(roi["x"]),
            float(geometry["center_y"]) - float(roi["y"]),
        )
        matrix = self._cv2.getRotationMatrix2D(
            center, float(geometry["angle_degrees"]), 1.0
        )
        aligned = self._cv2.warpAffine(
            crop,
            matrix,
            (crop.shape[1], crop.shape[0]),
            flags=self._cv2.INTER_LINEAR,
            borderMode=self._cv2.BORDER_REFLECT_101,
        )
        gray = self._cv2.cvtColor(aligned, self._cv2.COLOR_BGR2GRAY)
        iris_radius = max(
            min(float(geometry["iris_width"]), float(geometry["iris_height"]))
            * 0.5,
            4.0,
        )
        # Daugman-style rubber-sheet normalization: unwrap the annulus into a
        # fixed polar texture. The pupil boundary is conservatively estimated
        # as 25% of the fitted iris radius; the segmentation stage already
        # required a coherent, centered pupil before this function is called.
        polar = self._cv2.warpPolar(
            gray,
            (64, 256),
            center,
            iris_radius,
            self._cv2.WARP_POLAR_LINEAR + self._cv2.WARP_FILL_OUTLIERS,
        )
        inner = max(int(round(64 * 0.25)), 1)
        outer = max(int(round(64 * 0.95)), inner + 1)
        annulus = polar[:, inner:outer]
        normalized = self._cv2.resize(
            annulus,
            (32, 128),
            interpolation=self._cv2.INTER_AREA,
        ).T
        normalized = self._cv2.equalizeHist(normalized).astype(self._np.float32)
        normalized -= float(normalized.mean())
        deviation = float(normalized.std())
        if deviation < 1e-6:
            raise BiometricProcessingError(
                "The segmented iris did not contain enough texture detail."
            )
        normalized /= deviation
        return _normalize_vector(normalized.flatten().astype(float).tolist())

    def _extract_onnx_candidate(self, image) -> IrisCandidate:
        assert self._cv2 is not None
        assert self._np is not None
        assert self._Image is not None
        try:
            height, width = image.shape[:2]
            input_size = int(settings.IRIS_ONNX_INPUT_SIZE)
            rgb = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2RGB)
            blob = self._cv2.dnn.blobFromImage(
                rgb,
                scalefactor=1.0 / 255.0,
                size=(input_size, input_size),
                mean=(0.0, 0.0, 0.0),
                swapRB=False,
                crop=False,
            )
            with self._onnx_inference_lock:
                self._onnx_net.setInput(blob)
                output = self._onnx_net.forward()
            mask = self._np.squeeze(output)

            if mask.ndim == 3 and mask.shape[0] <= 8:
                mask = self._np.argmax(mask, axis=0) if mask.shape[0] > 1 else mask[0]
            elif mask.ndim == 3 and mask.shape[-1] <= 8:
                mask = self._np.argmax(mask, axis=-1) if mask.shape[-1] > 1 else mask[..., 0]
            if mask.ndim != 2:
                raise BiometricProcessingError("The local iris ONNX output shape is unsupported.")

            mask = mask.astype(self._np.float32)
            span = float(mask.max() - mask.min())
            if span > 1e-6:
                mask = (mask - mask.min()) / span
            threshold = min(0.85, max(0.45, float(mask.mean() + mask.std() * 0.4)))
            binary = mask >= threshold
            if int(binary.sum()) < 25:
                binary = mask >= 0.5
            if int(binary.sum()) < 25:
                raise BiometricProcessingError("The local iris ONNX model did not produce a usable iris mask.")

            ys, xs = self._np.where(binary)
            mask_height, mask_width = mask.shape[:2]
            x0 = int(xs.min() / max(mask_width - 1, 1) * width)
            x1 = int(xs.max() / max(mask_width - 1, 1) * width)
            y0 = int(ys.min() / max(mask_height - 1, 1) * height)
            y1 = int(ys.max() / max(mask_height - 1, 1) * height)
            pad = max(int(max(x1 - x0, y1 - y0) * 1.6), 24)
            center_x = (x0 + x1) // 2
            center_y = (y0 + y1) // 2
            crop_x0 = max(center_x - pad, 0)
            crop_x1 = min(center_x + pad, width)
            crop_y0 = max(center_y - pad, 0)
            crop_y1 = min(center_y + pad, height)
            crop = image[crop_y0:crop_y1, crop_x0:crop_x1]
            if crop.size == 0:
                raise BiometricProcessingError("The local iris ONNX crop was empty.")

            radius = float(max(x1 - x0, y1 - y0, 4)) / 2.0
            image_min_side = float(min(height, width))
            quality_score = self._quality_score_pretrained(crop, radius, image_min_side)
            embedding = self._build_embedding_pretrained(crop, radius, image_min_side)
            gray = self._cv2.cvtColor(
                self._cv2.resize(crop, (96, 96)),
                self._cv2.COLOR_BGR2GRAY,
            )
            grayscale = [float(value) for value in gray.flatten().tolist()]
            return IrisCandidate(
                center_x=float(center_x) / float(width),
                center_y=float(center_y) / float(height),
                radius=radius,
                quality_score=quality_score,
                embedding=embedding,
                grayscale=grayscale,
            )
        except Exception as exc:
            self._load_error = exc
            pil_image = self._Image.fromarray(
                self._cv2.cvtColor(image, self._cv2.COLOR_BGR2RGB)
            ).convert("L")
            return self._extract_fallback_candidate(pil_image)

    def _run_onnx_for_eye_crops(self, crops: list[object]):
        """Run the existing Worldcoin model once for a batch of eye ROIs."""
        assert self._cv2 is not None
        assert self._np is not None
        blobs = []
        for crop in crops:
            gray = self._cv2.cvtColor(crop, self._cv2.COLOR_BGR2GRAY)
            resized = self._cv2.resize(
                gray,
                (
                    int(settings.IRIS_TRACKING_INPUT_WIDTH),
                    int(settings.IRIS_TRACKING_INPUT_HEIGHT),
                ),
                interpolation=self._cv2.INTER_LINEAR,
            )
            normalized = resized.astype(self._np.float32) / 255.0
            normalized = self._np.repeat(normalized[..., None], 3, axis=2)
            normalized -= self._np.array(
                [0.485, 0.456, 0.406], dtype=self._np.float32
            )
            normalized /= self._np.array(
                [0.229, 0.224, 0.225], dtype=self._np.float32
            )
            blobs.append(self._np.transpose(normalized, (2, 0, 1)))

        blob = self._np.stack(blobs).astype(self._np.float32)
        with self._onnx_inference_lock:
            self._onnx_net.setInput(blob)
            output = self._onnx_net.forward()
        if output.ndim != 4 or output.shape[0] != len(crops):
            raise BiometricProcessingError(
                "The iris segmentation model returned an unsupported batch shape."
            )
        if output.shape[1] == 4:
            return output
        if output.shape[-1] == 4:
            return self._np.transpose(output, (0, 3, 1, 2))
        raise BiometricProcessingError(
            "The iris segmentation model did not return its four semantic masks."
        )

    def _geometry_from_eye_mask(
        self,
        probabilities,
        roi: dict,
        frame_width: int,
        frame_height: int,
    ) -> dict | None:
        """Fit iris geometry in ROI pixels, then map it into frame pixels."""
        assert self._cv2 is not None
        assert self._np is not None
        mask = self._np.clip(
            self._np.nan_to_num(
                probabilities[1].astype(self._np.float32),
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            ),
            0.0,
            1.0,
        )
        binary = mask >= 0.5
        eyeball_binary = probabilities[0] >= 0.5
        pupil_binary = probabilities[2] >= 0.5
        if int(binary.sum()) < 25:
            return None

        component_count, labels, stats, _ = self._cv2.connectedComponentsWithStats(
            binary.astype(self._np.uint8), connectivity=8
        )
        mask_height, mask_width = mask.shape[:2]
        crop_width = int(roi["width"])
        crop_height = int(roi["height"])
        scale_x = crop_width / float(mask_width)
        scale_y = crop_height / float(mask_height)
        crop_area = float(crop_width * crop_height)
        component_order = sorted(
            range(1, component_count),
            key=lambda index: int(stats[index, self._cv2.CC_STAT_AREA]),
            reverse=True,
        )

        for component_index in component_order:
            component_area = int(stats[component_index, self._cv2.CC_STAT_AREA])
            area_ratio = component_area * scale_x * scale_y / max(crop_area, 1.0)
            if component_area < 25 or area_ratio > 0.60:
                continue
            component_bool = labels == component_index
            eyeball_coverage = float(eyeball_binary[component_bool].mean())
            pupil_inside = pupil_binary & component_bool
            pupil_area = int(pupil_inside.sum())
            pupil_ratio = pupil_area / float(component_area)
            if (
                eyeball_coverage < 0.78
                or pupil_area < max(8, int(component_area * 0.02))
                or pupil_ratio > 0.58
            ):
                continue

            pupil_count, pupil_labels, pupil_stats, _ = (
                self._cv2.connectedComponentsWithStats(
                    pupil_inside.astype(self._np.uint8), connectivity=8
                )
            )
            if pupil_count <= 1:
                continue
            pupil_index = max(
                range(1, pupil_count),
                key=lambda index: int(pupil_stats[index, self._cv2.CC_STAT_AREA]),
            )
            coherent_pupil_ratio = float(
                pupil_stats[pupil_index, self._cv2.CC_STAT_AREA]
            ) / max(float(pupil_area), 1.0)
            if coherent_pupil_ratio < 0.68:
                continue

            contours, _ = self._cv2.findContours(
                component_bool.astype(self._np.uint8),
                self._cv2.RETR_EXTERNAL,
                self._cv2.CHAIN_APPROX_NONE,
            )
            if not contours:
                continue
            contour = max(contours, key=self._cv2.contourArea)
            if len(contour) < 5:
                continue
            crop_contour = contour.astype(self._np.float32)
            crop_contour[:, 0, 0] *= scale_x
            crop_contour[:, 0, 1] *= scale_y
            source_area = float(self._cv2.contourArea(crop_contour))
            source_perimeter = float(self._cv2.arcLength(crop_contour, True))
            if source_area <= 0.0 or source_perimeter <= 0.0:
                continue

            (center_x, center_y), (iris_width, iris_height), angle = (
                self._cv2.fitEllipse(crop_contour)
            )
            iris_width = float(iris_width)
            iris_height = float(iris_height)
            if iris_width < 4.0 or iris_height < 4.0:
                continue
            axis_ratio = min(iris_width, iris_height) / max(iris_width, iris_height)
            relative_diameter = min(iris_width, iris_height) / max(
                float(min(crop_width, crop_height)), 1.0
            )
            if axis_ratio < 0.25 or relative_diameter < 0.10:
                continue

            pupil_y, pupil_x = self._np.where(pupil_labels == pupil_index)
            pupil_center_x = float(pupil_x.mean()) * scale_x
            pupil_center_y = float(pupil_y.mean()) * scale_y
            pupil_center_offset = math.hypot(
                pupil_center_x - float(center_x),
                pupil_center_y - float(center_y),
            ) / max(min(iris_width, iris_height) * 0.5, 1.0)
            if pupil_center_offset > 0.68:
                continue

            ellipse_area = math.pi * iris_width * iris_height * 0.25
            ellipse_coverage = _clamp(source_area / max(ellipse_area, 1.0))
            circularity = _clamp(
                (4.0 * math.pi * source_area)
                / (source_perimeter * source_perimeter)
            )
            if circularity < 0.30:
                continue
            foreground_strength = float(mask[component_bool].mean())
            confidence = _clamp(
                (foreground_strength * 0.30)
                + (eyeball_coverage * 0.18)
                + (coherent_pupil_ratio * 0.14)
                + (ellipse_coverage * 0.18)
                + (circularity * 0.12)
                + (axis_ratio * 0.08)
            )
            if confidence < 0.45:
                continue

            box_x, box_y, box_width, box_height = self._cv2.boundingRect(
                crop_contour
            )
            frame_contour = crop_contour[:, 0, :].copy()
            frame_contour[:, 0] += float(roi["x"])
            frame_contour[:, 1] += float(roi["y"])
            stride = max(1, len(frame_contour) // 64)
            return {
                "detected": True,
                "eye_side": roi["eye_side"],
                "confidence": _round4(confidence),
                "stable": confidence >= settings.IRIS_TRACKING_STABLE_CONFIDENCE,
                "center_x": _round4(float(center_x) + float(roi["x"])),
                "center_y": _round4(float(center_y) + float(roi["y"])),
                "iris_width": _round4(iris_width),
                "iris_height": _round4(iris_height),
                "radius": _round4((iris_width + iris_height) * 0.25),
                "angle_degrees": _round4(float(angle)),
                "circularity": _round4(circularity),
                "contour": [
                    [_round4(float(point[0])), _round4(float(point[1]))]
                    for point in frame_contour[::stride]
                ],
                "bounding_box": {
                    "x": _round4(float(box_x) + float(roi["x"])),
                    "y": _round4(float(box_y) + float(roi["y"])),
                    "width": _round4(float(box_width)),
                    "height": _round4(float(box_height)),
                },
                "eye_roi": {
                    key: roi[key] for key in ("x", "y", "width", "height")
                },
                "frame_width": frame_width,
                "frame_height": frame_height,
            }
        return None

    def track_iris(self, image_path: str) -> dict:
        """Localize eye ROIs with face landmarks and segment them with ONNX."""
        self._ensure_ready()
        assert self._cv2 is not None
        image = self._cv2.imread(image_path)
        if image is None:
            raise BiometricProcessingError(
                "The camera frame could not be read for iris tracking."
            )

        frame_height, frame_width = image.shape[:2]
        try:
            landmarks = self._detect_landmarks(image)
            rois = self._eye_rois_from_face_landmarks(image, landmarks)
            debug_rois = [
                {
                    "eye_side": roi["eye_side"],
                    **{key: roi[key] for key in ("x", "y", "width", "height")},
                }
                for roi in rois
            ]
            if not rois:
                return {
                    "detected": False,
                    "confidence": 0.0,
                    "eyes": [],
                    "eye_rois": [],
                    "frame_width": frame_width,
                    "frame_height": frame_height,
                }

            outputs = self._run_onnx_for_eye_crops([roi["crop"] for roi in rois])
            eyes = []
            for probabilities, roi in zip(outputs, rois):
                geometry = self._geometry_from_eye_mask(
                    probabilities, roi, frame_width, frame_height
                )
                if geometry is not None:
                    eyes.append(geometry)

            response = {
                "detected": bool(eyes),
                "confidence": max(
                    (float(eye["confidence"]) for eye in eyes), default=0.0
                ),
                "eyes": eyes,
                "eye_rois": debug_rois,
                "frame_width": frame_width,
                "frame_height": frame_height,
            }
            if eyes:
                primary = max(eyes, key=lambda eye: float(eye["confidence"]))
                response.update(primary)
                response["eyes"] = eyes
                response["eye_rois"] = debug_rois
            return response
        except BiometricProcessingError:
            raise
        except Exception as exc:
            raise BiometricProcessingError(
                "The live eye ROI or iris segmentation stage failed."
            ) from exc

    def _extract_pretrained_candidates(self, image) -> list[IrisCandidate]:
        groups = self._group_iris_landmarks(self._detect_landmarks(image))
        candidates: list[IrisCandidate] = []
        for group in groups:
            cropped = self._crop_from_group(image, group)
            if cropped is None:
                continue
            crop = cropped["crop"]
            radius = cropped["radius"]
            image_min_side = cropped["image_min_side"]
            quality_score = self._quality_score_pretrained(crop, radius, image_min_side)
            embedding = self._build_embedding_pretrained(crop, radius, image_min_side)
            gray = self._cv2.cvtColor(
                self._cv2.resize(crop, (96, 96)),
                self._cv2.COLOR_BGR2GRAY,
            )
            grayscale = [float(value) for value in gray.flatten().tolist()]
            candidates.append(
                IrisCandidate(
                    center_x=cropped["center_x"],
                    center_y=cropped["center_y"],
                    radius=radius,
                    quality_score=quality_score,
                    embedding=embedding,
                    grayscale=grayscale,
                )
            )
        return candidates

    def _select_primary_candidate(
        self,
        candidates: list[IrisCandidate],
        eye_side: str,
    ) -> IrisCandidate | None:
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        ranked = sorted(
            candidates,
            key=lambda candidate: (candidate.quality_score * 0.55) + candidate.radius,
            reverse=True,
        )
        if abs(
            ((ranked[0].quality_score * 0.55) + ranked[0].radius)
            - ((ranked[1].quality_score * 0.55) + ranked[1].radius)
        ) < 0.2:
            ordered = sorted(candidates, key=lambda candidate: candidate.center_x)
            return ordered[0] if eye_side == "LEFT" else ordered[-1]
        return ranked[0]

    def extract_features(self, image_path: str, eye_side: str = "LEFT") -> IrisSample:
        self._ensure_ready()

        if self._mode == "heuristic":
            image = self._read_image(image_path)
            candidate = self._extract_fallback_candidate(image)
            return IrisSample(
                iris_detected=candidate.quality_score >= 0.2,
                quality_score=candidate.quality_score,
                embedding=candidate.embedding,
                detection_confidence=candidate.quality_score,
            )

        assert self._cv2 is not None
        image = self._cv2.imread(image_path)
        if image is None:
            raise BiometricProcessingError("The uploaded iris image could not be read.")

        if self._mode == "local_onnx":
            # Enrollment and authentication use the same real eye-ROI path as
            # live tracking. The Worldcoin mask must validate the iris before
            # a pattern is stored or compared; never fall back to a full-frame
            # or fixed-position estimate.
            landmarks = self._detect_landmarks(image)
            rois = self._eye_rois_from_face_landmarks(image, landmarks)
            selected = next(
                (roi for roi in rois if roi["eye_side"] == eye_side),
                None,
            )
            if selected is None:
                return IrisSample(False, 0.0, [], 0.0)
            probabilities = self._run_onnx_for_eye_crops([selected["crop"]])[0]
            height, width = image.shape[:2]
            geometry = self._geometry_from_eye_mask(
                probabilities, selected, width, height
            )
            if geometry is None:
                return IrisSample(False, 0.0, [], 0.0)
            radius = float(geometry["radius"])
            candidate = IrisCandidate(
                center_x=float(geometry["center_x"]) / float(width),
                center_y=float(geometry["center_y"]) / float(height),
                radius=radius,
                quality_score=self._quality_score_pretrained(
                    selected["crop"], radius, float(min(height, width))
                ),
                embedding=self._build_segmented_iris_embedding(
                    selected["crop"], geometry, selected
                ),
                grayscale=[],
            )
            detection_confidence = float(geometry["confidence"])
        else:
            candidate = self._select_primary_candidate(
                self._extract_pretrained_candidates(image),
                eye_side,
            )
            detection_confidence = candidate.quality_score if candidate else 0.0
        if candidate is None:
            return IrisSample(
                iris_detected=False,
                quality_score=0.0,
                embedding=[],
                detection_confidence=0.0,
            )
        return IrisSample(
            iris_detected=True,
            quality_score=candidate.quality_score,
            embedding=candidate.embedding,
            detection_confidence=detection_confidence,
        )

    def compare(
        self,
        image_path: str,
        reference_embedding: list[float],
        eye_side: str = "LEFT",
    ) -> dict:
        sample = self.extract_features(image_path=image_path, eye_side=eye_side)
        if not sample.iris_detected:
            message = "The iris could not be processed. Move closer, improve the lighting and try again."
            return {
                "iris": {
                    "iris_detected": False,
                    "quality_score": sample.quality_score,
                    "detection_confidence": sample.detection_confidence,
                    "raw_score": 0.0,
                    "normalized_score": 0.0,
                    "threshold": settings.IRIS_SIMILARITY_THRESHOLD,
                    "passed": False,
                    "message": message,
                },
                "message": message,
            }

        raw_score = _cosine_similarity(sample.embedding, reference_embedding)
        normalized_score = _clamp((raw_score + 1.0) / 2.0)
        quality_ok = sample.quality_score >= settings.IRIS_QUALITY_THRESHOLD
        match_ok = normalized_score >= settings.IRIS_SIMILARITY_THRESHOLD
        passed = sample.iris_detected and quality_ok and match_ok

        if not quality_ok:
            message = "The iris could not be processed. Move closer, improve the lighting and try again."
        elif not match_ok:
            message = "Iris did not match the reference template."
        else:
            message = "Iris quality verification and template comparison passed."

        return {
            "iris": {
                "iris_detected": sample.iris_detected,
                "quality_score": sample.quality_score,
                "detection_confidence": sample.detection_confidence,
                "raw_score": _round4(raw_score),
                "normalized_score": _round4(normalized_score),
                "threshold": settings.IRIS_SIMILARITY_THRESHOLD,
                "passed": passed,
                "message": message,
            },
            "message": message,
        }

    def aggregate_samples(
        self,
        samples: list[IrisSample],
        *,
        minimum_samples: int | None = None,
    ) -> list[float]:
        required = max(1, minimum_samples or settings.MIN_IRIS_SAMPLES)
        valid = [sample for sample in samples if sample.iris_detected and sample.embedding]
        if len(valid) < required:
            raise BiometricProcessingError(
                f"At least {required} valid iris sample(s) are required."
            )
        dimension = len(valid[0].embedding)
        if any(len(sample.embedding) != dimension for sample in valid):
            raise BiometricProcessingError("Iris template dimensions were inconsistent.")
        reference = valid[0].embedding
        aligned = [reference]
        # Polar templates are 32 radial rows x 128 angular columns. Compensate
        # for small eye/camera rotations before averaging enrollment samples.
        if dimension == 32 * 128:
            assert self._np is not None
            reference_matrix = self._np.asarray(reference).reshape(32, 128)
            for sample in valid[1:]:
                matrix = self._np.asarray(sample.embedding).reshape(32, 128)
                best = max(
                    range(-8, 9),
                    key=lambda shift: _cosine_similarity(
                        self._np.roll(matrix, shift, axis=1).flatten().tolist(),
                        reference_matrix.flatten().tolist(),
                    ),
                )
                aligned.append(
                    self._np.roll(matrix, best, axis=1).flatten().astype(float).tolist()
                )
        else:
            aligned.extend(sample.embedding for sample in valid[1:])
        weights = [max(sample.quality_score, 0.05) for sample in valid]
        total = sum(weights)
        aggregate = [
            sum(vector[index] * weight for vector, weight in zip(aligned, weights)) / total
            for index in range(dimension)
        ]
        return _normalize_vector(aggregate)

    def compare_samples(
        self,
        samples: list[IrisSample],
        reference_embedding: list[float],
        *,
        minimum_samples: int | None = None,
    ) -> dict:
        required = max(1, minimum_samples or settings.MIN_IRIS_SAMPLES)
        valid = [sample for sample in samples if sample.iris_detected and sample.embedding]
        quality = _mean([sample.quality_score for sample in valid])
        confidence = _mean([sample.detection_confidence for sample in valid])
        if len(valid) < required:
            return {
                "iris": {
                    "iris_detected": bool(valid),
                    "quality_score": _round4(quality),
                    "detection_confidence": _round4(confidence),
                    "raw_score": 0.0,
                    "normalized_score": 0.0,
                    "threshold": settings.IRIS_SIMILARITY_THRESHOLD,
                    "sample_count": len(valid),
                    "valid_measurement": False,
                    "passed": False,
                    "message": f"At least {required} stable iris sample(s) are required.",
                }
            }
        probe = self.aggregate_samples(valid, minimum_samples=required)
        scores = [_cosine_similarity(probe, reference_embedding)]
        if len(probe) == 32 * 128 and len(reference_embedding) == len(probe):
            assert self._np is not None
            matrix = self._np.asarray(probe).reshape(32, 128)
            reference = self._np.asarray(reference_embedding).reshape(32, 128)
            scores = [
                _cosine_similarity(
                    self._np.roll(matrix, shift, axis=1).flatten().tolist(),
                    reference.flatten().tolist(),
                )
                for shift in range(-8, 9)
            ]
        raw_score = max(scores)
        normalized_score = _clamp((raw_score + 1.0) / 2.0)
        passed = normalized_score >= settings.IRIS_SIMILARITY_THRESHOLD
        return {
            "iris": {
                "iris_detected": True,
                "quality_score": _round4(quality),
                "quality_threshold": settings.IRIS_QUALITY_THRESHOLD,
                "detection_confidence": _round4(confidence),
                "raw_score": _round4(raw_score),
                "normalized_score": _round4(normalized_score),
                "similarity_score": _round4(normalized_score),
                "threshold": settings.IRIS_SIMILARITY_THRESHOLD,
                "sample_count": len(valid),
                "valid_measurement": True,
                "passed": passed,
                "message": "Iris matched the enrolled template." if passed else "Iris did not match the enrolled template.",
            }
        }

    def evaluate_blink(
        self,
        open_image_path: str,
        blink_image_path: str,
        eye_side: str = "LEFT",
    ) -> dict:
        self._ensure_ready()

        if self._mode == "heuristic":
            open_image = self._read_image(open_image_path)
            blink_image = self._read_image(blink_image_path)
            open_candidate = self._extract_fallback_candidate(open_image)
            blink_candidate = self._extract_fallback_candidate(blink_image)
        else:
            assert self._cv2 is not None
            open_image = self._cv2.imread(open_image_path)
            blink_image = self._cv2.imread(blink_image_path)
            if open_image is None or blink_image is None:
                raise BiometricProcessingError(
                    "The blink challenge images could not be processed."
                )
            if self._mode == "local_onnx":
                open_candidate = self._extract_onnx_candidate(open_image)
                blink_candidate = self._extract_onnx_candidate(blink_image)
            else:
                open_candidate = self._select_primary_candidate(
                    self._extract_pretrained_candidates(open_image),
                    eye_side,
                )
                blink_candidates = self._extract_pretrained_candidates(blink_image)
                blink_candidate = None
                if open_candidate is not None and blink_candidates:
                    blink_candidate = min(
                        blink_candidates,
                        key=lambda candidate: math.hypot(
                            candidate.center_x - open_candidate.center_x,
                            candidate.center_y - open_candidate.center_y,
                        ),
                    )

        if open_candidate is None:
            message = "Open-eye capture failed. Keep one eye centered and try again."
            return {
                "iris": {
                    "iris_detected": False,
                    "blink_detected": False,
                    "quality_score": 0.0,
                    "raw_score": 0.0,
                    "normalized_score": 0.0,
                    "threshold": 0.55,
                    "passed": False,
                    "message": message,
                },
                "message": message,
            }

        open_quality = open_candidate.quality_score
        if blink_candidate is None:
            diff_score = 1.0
            blink_quality = 0.0
            motion_bonus = 0.30
        else:
            differences = [
                abs(left - right)
                for left, right in zip(open_candidate.grayscale, blink_candidate.grayscale)
            ]
            diff_score = _clamp((_mean(differences) / 18.0))
            blink_quality = blink_candidate.quality_score
            motion_bonus = 0.05

        quality_hint = _clamp((open_quality + blink_quality) / 2.0)
        blink_confidence = _round4(
            _clamp((diff_score * 0.70) + (quality_hint * 0.25) + motion_bonus)
        ) or 0.0

        passed = (
            open_quality >= settings.IRIS_QUALITY_THRESHOLD and blink_confidence >= 0.55
        )

        if open_quality < settings.IRIS_QUALITY_THRESHOLD:
            message = "Open-eye capture quality was too low. Improve the lighting and try again."
        elif blink_confidence < 0.55:
            message = "Blink challenge failed. Look at the camera, blink once, and try again."
        else:
            message = "Blink challenge completed successfully."

        return {
            "iris": {
                "iris_detected": True,
                "blink_detected": passed,
                "quality_score": _round4((open_quality + blink_quality) / 2.0),
                "raw_score": _round4(diff_score),
                "normalized_score": blink_confidence,
                "threshold": 0.55,
                "passed": passed,
                "message": message,
            },
            "message": message,
        }

@lru_cache(maxsize=1)
def get_voice_engine() -> VoiceBiometricEngine:
    return VoiceBiometricEngine()


@lru_cache(maxsize=1)
def get_iris_engine() -> IrisBiometricEngine:
    return IrisBiometricEngine()


def _close_cached_engines() -> None:
    if get_iris_engine.cache_info().currsize == 0:
        return
    try:
        get_iris_engine().close()
    except Exception:
        pass


atexit.register(_close_cached_engines)







