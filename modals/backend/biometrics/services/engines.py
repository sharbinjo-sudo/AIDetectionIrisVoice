from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
import struct
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


@dataclass
class IrisSample:
    iris_detected: bool
    quality_score: float
    embedding: list[float]


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
            from speechbrain.utils.fetching import LocalStrategy
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
        sources.append(("pretrained", settings.VOICE_MODEL_SOURCE, str(cache_dir)))

        load_errors: list[str] = []
        for mode, source, savedir in sources:
            try:
                self._classifier = EncoderClassifier.from_hparams(
                    source=source,
                    savedir=savedir,
                    run_opts={"device": "cpu"},
                    local_strategy=LocalStrategy.COPY,
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
        return True

    @property
    def mode(self) -> str:
        return self._mode

    def health(self) -> dict:
        detail = None
        if self._mode not in {"pretrained", "local_pretrained"} and self._load_error is not None:
            detail = f"Using heuristic voice fallback. Pretrained load detail: {self._load_error}"
        return {
            "ready": True,
            "name": self.name if self._mode in {"pretrained", "local_pretrained"} else "Heuristic Voice Analyzer",
            "mode": self._mode,
            "source": self._source,
            "cache_dir": str(settings.VOICE_MODEL_CACHE_DIR),
            "detail": detail,
        }

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
        )

    def extract_features(self, audio_path: str) -> VoiceSample:
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

        tensor = self._torch.tensor(signal_values, dtype=self._torch.float32).unsqueeze(0)
        try:
            with self._torch.no_grad():
                embedding_tensor = self._classifier.encode_batch(tensor)
            embedding = embedding_tensor.squeeze().cpu().numpy().astype(float).tolist()
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
        )

    def compare(self, audio_path: str, reference_embedding: list[float]) -> dict:
        sample = self.extract_features(audio_path)
        raw_score = _cosine_similarity(sample.embedding, reference_embedding)
        normalized_score = _clamp((raw_score + 1.0) / 2.0)
        quality_ok = sample.quality_score >= settings.VOICE_QUALITY_THRESHOLD
        activity_ok = sample.speech_activity_score >= settings.VOICE_ACTIVITY_THRESHOLD
        match_ok = normalized_score >= settings.VOICE_SIMILARITY_THRESHOLD
        passed = quality_ok and activity_ok and match_ok

        if sample.duration_seconds < settings.VOICE_MIN_SECONDS:
            message = "The recording was too quiet or too short. Speak clearly and try again."
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

    def __init__(self):
        self._load_error = None
        self._cv2 = None
        self._mp = None
        self._np = None
        self._Image = None
        self._landmarker = None
        self._onnx_net = None
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
                return
        except Exception as exc:
            self._load_error = exc

        try:
            if self._cv2 is None or self._np is None:
                raise RuntimeError("OpenCV and NumPy are required for MediaPipe iris loading.")
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
        except Exception as exc:
            self._load_error = exc
            return

        self._mp = mp

        try:
            model_path = ensure_remote_asset(
                destination=self._model_path,
                description="iris model",
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
            self._mode = "pretrained"
            self._source = settings.IRIS_MODEL_URL
            self._load_error = None
        except Exception as exc:
            self._load_error = exc

    @property
    def ready(self) -> bool:
        return self._Image is not None

    @property
    def mode(self) -> str:
        return self._mode

    def health(self) -> dict:
        detail = None
        if self._mode == "heuristic" and self._load_error is not None:
            detail = f"Using heuristic iris fallback. Pretrained load detail: {self._load_error}"
        model_name = {
            "local_onnx": "Local Iris ONNX Segmenter",
            "pretrained": "MediaPipe Face Landmarker",
        }.get(self._mode, "Heuristic Iris Analyzer")
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
                "The iris verification engine is not ready. Install Pillow or the backend image dependencies and restart the server."
            )

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
        result = self._landmarker.detect(mp_image)
        if not result.face_landmarks:
            return []
        return result.face_landmarks[0]

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
            )

        assert self._cv2 is not None
        image = self._cv2.imread(image_path)
        if image is None:
            raise BiometricProcessingError("The uploaded iris image could not be read.")

        if self._mode == "local_onnx":
            candidate = self._extract_onnx_candidate(image)
        else:
            candidate = self._select_primary_candidate(
                self._extract_pretrained_candidates(image),
                eye_side,
            )
        if candidate is None:
            return IrisSample(
                iris_detected=False,
                quality_score=0.0,
                embedding=[],
            )
        return IrisSample(
            iris_detected=True,
            quality_score=candidate.quality_score,
            embedding=candidate.embedding,
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
                "raw_score": _round4(raw_score),
                "normalized_score": _round4(normalized_score),
                "threshold": settings.IRIS_SIMILARITY_THRESHOLD,
                "passed": passed,
                "message": message,
            },
            "message": message,
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







