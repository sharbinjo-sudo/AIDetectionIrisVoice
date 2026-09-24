"""Calibrate fusion decision thresholds from genuine and impostor samples.

Expected input files (JSON):

    # genuine-user captures: one entry per capture session
    {
      "samples": [
        {"face": {"similarity_score": 0.89, "quality_score": 0.86,
                  "detection_confidence": 0.97},
         "iris": {"similarity_score": 0.82, "quality_score": 0.71,
                  "detection_confidence": 1.0},
         "voice": {"similarity_score": 0.91, "quality_score": 0.9,
                   "speech_activity_score": 0.8},
         "label": "genuine"},             // optional, file already implies it
        ...
      ]
    }

Impostor / presentation-attack samples use the same shape. The command
recomputes the three-modal reliability-weighted fusion score for every sample,
sweeps candidate thresholds, and
picks the operating point that maximises Youden's J (TPR - FPR) subject to
`--max-fpr`. Samples that fail a capture-quality gate are excluded rather than
being treated as impostor evidence. Face, iris, and voice must all be present;
this command never invents calibration data for a missing modality.

The result is written to ``FUSION_CALIBRATION_PATH`` (or ``--output``) and is
loaded automatically by the authentication workflow.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from biometrics.services.fusion import (
    ModalityMeasurement,
    modality_reliability,
    quality_gate_open,
)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _measurement(modality: dict) -> ModalityMeasurement:
    return ModalityMeasurement(
        score=_clamp(
            modality.get(
                "similarity_score",
                modality.get("score", modality.get("quality_score", 0.0)),
            )
        ),
        quality=_clamp(modality.get("quality_score", 0.0)),
        detection_confidence=_clamp(
            modality.get("detection_confidence", 1.0 if modality else 0.0)
        ),
        valid_measurement=False,
        speech_activity=(
            None
            if modality.get("speech_activity_score") is None
            else _clamp(modality["speech_activity_score"])
        ),
    )


def _fusion_score(sample: dict, options: dict) -> float | None:
    """Recompute the strict three-modal, quality-aware fusion score."""
    face_raw = sample.get("face") or {}
    iris_raw = sample.get("iris") or {}
    voice_raw = sample.get("voice") or {}
    face = _measurement(face_raw)
    iris = _measurement(iris_raw)
    voice = _measurement(voice_raw)
    if voice.speech_activity is not None:
        voice.detection_confidence = 1.0

    face_valid = quality_gate_open(
        face.quality,
        face.detection_confidence,
        options["face_quality_threshold"],
        0.0,
    )
    iris_valid = quality_gate_open(
        iris.quality,
        iris.detection_confidence,
        options["iris_quality_threshold"],
        options["iris_detection_confidence_threshold"],
    )
    voice_valid = quality_gate_open(
        voice.quality,
        voice.detection_confidence,
        options["voice_quality_threshold"],
        0.0,
    ) and (
        voice.speech_activity is None
        or voice.speech_activity >= options["voice_activity_threshold"]
    )

    if not (face_valid and iris_valid and voice_valid):
        return None
    weighted_face = max(
        options["base_face_weight"]
        * modality_reliability(face.quality, face.detection_confidence),
        1e-6,
    )
    weighted_iris = max(
        options["base_iris_weight"]
        * modality_reliability(iris.quality, iris.detection_confidence),
        1e-6,
    )
    weighted_voice = max(
        options["base_voice_weight"]
        * modality_reliability(voice.quality, voice.detection_confidence),
        1e-6,
    )
    total = weighted_face + weighted_iris + weighted_voice
    return _clamp(
        (
            face.score * weighted_face
            + iris.score * weighted_iris
            + voice.score * weighted_voice
        )
        / total
    )


def _load_samples(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError(f"Could not read {path}: {exc}") from exc
    samples = data.get("samples", data) if isinstance(data, dict) else data
    if not isinstance(samples, list) or not samples:
        raise CommandError(f"{path} contains no samples.")
    return [sample for sample in samples if isinstance(sample, dict)]


class Command(BaseCommand):
    help = (
        "Calibrate fusion thresholds from genuine-user and impostor samples "
        "and write the calibration JSON used by the authentication workflow."
    )

    def add_arguments(self, parser):
        parser.add_argument("--genuine", required=True, help="Genuine samples JSON")
        parser.add_argument("--impostor", required=True, help="Impostor samples JSON")
        parser.add_argument(
            "--max-fpr",
            type=float,
            default=0.02,
            help="Maximum tolerated impostor accept rate (default 0.02).",
        )
        parser.add_argument(
            "--output",
            default=None,
            help="Output path (defaults to FUSION_CALIBRATION_PATH).",
        )

    def handle(self, *args, **options):
        options_map = {
            "base_face_weight": settings.FUSION_FACE_WEIGHT,
            "base_voice_weight": settings.FUSION_VOICE_WEIGHT,
            "base_iris_weight": settings.FUSION_IRIS_WEIGHT,
            "face_quality_threshold": settings.FACE_QUALITY_THRESHOLD,
            "iris_quality_threshold": settings.IRIS_QUALITY_THRESHOLD,
            "iris_detection_confidence_threshold": (
                settings.IRIS_DETECTION_CONFIDENCE_THRESHOLD
            ),
            "voice_quality_threshold": settings.VOICE_QUALITY_THRESHOLD,
            "voice_activity_threshold": settings.VOICE_ACTIVITY_THRESHOLD,
        }

        genuine_scores: list[float] = []
        impostor_scores: list[float] = []

        for sample in _load_samples(Path(options["genuine"])):
            score = _fusion_score(sample, options_map)
            if score is None:
                self.stdout.write(
                    self.style.WARNING(
                        "Skipping genuine sample with no valid modality: "
                        f"{sample}"
                    )
                )
                continue
            genuine_scores.append(score)

        for sample in _load_samples(Path(options["impostor"])):
            score = _fusion_score(sample, options_map)
            if score is not None:
                impostor_scores.append(score)

        if not genuine_scores or not impostor_scores:
            raise CommandError(
                "Calibration needs at least one scoreable genuine and one "
                "scoreable impostor sample."
            )

        max_fpr = _clamp(options["max_fpr"])
        candidates = sorted(set(genuine_scores + impostor_scores), reverse=True)
        best_threshold = max(candidates) + 1e-9
        best_j = -2.0
        roc_points = []
        for threshold in candidates:
            tpr = sum(s >= threshold for s in genuine_scores) / len(genuine_scores)
            fpr = sum(s >= threshold for s in impostor_scores) / len(impostor_scores)
            roc_points.append(
                {"threshold": round(threshold, 4), "tpr": round(tpr, 4), "fpr": round(fpr, 4)}
            )
            j = tpr - fpr
            if fpr <= max_fpr and j > best_j:
                best_j = j
                best_threshold = threshold

        if best_j <= 0:
            raise CommandError(
                "No threshold separates genuine and impostor samples within "
                f"max-fpr={max_fpr}. Collect more representative samples."
            )

        output_path = Path(
            options["output"] or settings.FUSION_CALIBRATION_PATH
        )
        payload = {
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
            "genuine_samples": len(genuine_scores),
            "impostor_samples": len(impostor_scores),
            "fusion_threshold": round(_clamp(best_threshold), 4),
            # Kept for backward compatibility with the separate two-modal
            # quality-test endpoint. Three-modal authentication never falls
            # back to one modality.
            "single_modality_fallback_threshold": round(
                settings.FUSION_SINGLE_MODALITY_FALLBACK_THRESHOLD, 4
            ),
            "youden_j": round(best_j, 4),
            "max_fpr": max_fpr,
            "tpr_at_threshold": round(
                sum(s >= best_threshold for s in genuine_scores)
                / len(genuine_scores),
                4,
            ),
            "fpr_at_threshold": round(
                sum(s >= best_threshold for s in impostor_scores)
                / len(impostor_scores),
                4,
            ),
            "roc": roc_points,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote calibration to {output_path}: "
                f"fusion_threshold={payload['fusion_threshold']}, "
                f"(TPR={payload['tpr_at_threshold']}, "
                f"FPR={payload['fpr_at_threshold']})."
            )
        )
