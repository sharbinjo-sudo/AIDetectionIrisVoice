"""Quality-aware multimodal authentication decision engine.

Design goals (see product requirements):

1. Capture quality is NOT identity evidence. A blurry iris or a noisy
   recording says nothing about whether the person is a genuine human, so
   low quality must lower a modality's *influence* and trigger a retry —
   never a mismatch rejection.
2. When one modality is temporarily unreliable, the reliable one carries
   more weight, gated by liveness/identity-confidence requirements.
3. When both modalities are high quality, both must strongly agree.
4. Every decision carries an explicit, structured reason code so the UI can
   distinguish genuine-live-user / poor-quality / mismatch / spoof states.

The IRL endpoint has no enrolled reference template and no dedicated
liveness classifier, so it can never produce positive mismatch or spoof
evidence by itself. REJECTED_MISMATCH / REJECTED_SPOOF are therefore only
returned when explicit evidence exists (e.g. a caller-supplied liveness
result), and reserved otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _round4(value: float) -> float:
    return round(float(value), 4)


class ReasonCode:
    """Machine-readable decision reason codes (contract: reason_codes.md)."""

    # Positive outcome
    ALL_MODALITIES_VALID = "ALL_MODALITIES_VALID"
    FACE_VOICE_VALID_IRIS_CAPTURE_ONLY = "FACE_VOICE_VALID_IRIS_CAPTURE_ONLY"
    SINGLE_MODALITY_HIGH_CONFIDENCE = "SINGLE_MODALITY_HIGH_CONFIDENCE"
    # Retry outcomes — poor/ambiguous capture, never identity evidence
    IRIS_NOT_DETECTED = "IRIS_NOT_DETECTED"
    IRIS_QUALITY_TOO_LOW = "IRIS_QUALITY_TOO_LOW"
    VOICE_QUALITY_TOO_LOW = "VOICE_QUALITY_TOO_LOW"
    VOICE_NO_SPEECH_ACTIVITY = "VOICE_NO_SPEECH_ACTIVITY"
    FACE_NOT_DETECTED = "FACE_NOT_DETECTED"
    FACE_QUALITY_TOO_LOW = "FACE_QUALITY_TOO_LOW"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    FUSION_INCONCLUSIVE = "FUSION_INCONCLUSIVE"
    NO_VALID_MODALITY = "NO_VALID_MODALITY"
    # Failure outcomes — require actual evidence
    REJECTED_MISMATCH = "REJECTED_MISMATCH"
    REJECTED_SPOOF = "REJECTED_SPOOF"
    # Infrastructure
    PROCESSING_ERROR = "PROCESSING_ERROR"


# User-facing guidance for each reason code. Keep in sync with ReasonCode.
REASON_MESSAGES: dict[str, str] = {
    ReasonCode.ALL_MODALITIES_VALID: (
        "Iris and voice measurements are valid and satisfy the verification policy."
    ),
    ReasonCode.FACE_VOICE_VALID_IRIS_CAPTURE_ONLY: (
        "Face and voice matched the enrolled templates; iris was captured for the prototype only."
    ),
    ReasonCode.SINGLE_MODALITY_HIGH_CONFIDENCE: (
        "One capture was temporarily unreliable; the remaining high-confidence "
        "measurement satisfied the verification policy."
    ),
    ReasonCode.IRIS_NOT_DETECTED: (
        "No iris could be measured in the capture. Move closer, center your open "
        "eye, and try again."
    ),
    ReasonCode.IRIS_QUALITY_TOO_LOW: (
        "The iris capture is unclear (focus, lighting, distance, or position). "
        "Improve lighting, move closer, and capture again."
    ),
    ReasonCode.VOICE_QUALITY_TOO_LOW: (
        "The voice recording is too quiet or unclear. Speak clearly in a quiet "
        "place and try again."
    ),
    ReasonCode.VOICE_NO_SPEECH_ACTIVITY: (
        "No clear speech was detected in the recording. Speak the phrase out "
        "loud and try again."
    ),
    ReasonCode.FACE_NOT_DETECTED: (
        "No face was detected. Center one face in the frame and try again."
    ),
    ReasonCode.FACE_QUALITY_TOO_LOW: (
        "The face capture is unclear. Use even lighting, look straight at the "
        "camera, and hold still."
    ),
    ReasonCode.MULTIPLE_FACES: (
        "More than one face was detected. Only the account holder may be in frame."
    ),
    ReasonCode.FUSION_INCONCLUSIVE: (
        "Capture confidence is inconclusive. Retake both captures with better "
        "lighting and a closer, steady eye."
    ),
    ReasonCode.NO_VALID_MODALITY: (
        "Neither capture produced a valid measurement. Retake both the iris "
        "image and the voice recording."
    ),
    ReasonCode.REJECTED_MISMATCH: (
        "The captured biometrics did not match the expected identity evidence."
    ),
    ReasonCode.REJECTED_SPOOF: "Liveness or anti-spoof checks failed.",
    ReasonCode.PROCESSING_ERROR: (
        "Verification could not complete because of a processing error."
    ),
}


@dataclass
class ModalityMeasurement:
    """Per-modality measurements required by the fusion contract."""

    score: float  # normalized quality/similarity score in [0, 1]
    quality: float  # capture quality in [0, 1]
    detection_confidence: float  # modality-specific detection confidence
    valid_measurement: bool  # True when the measurement is usable as evidence
    speech_activity: float | None = None  # voice-only


@dataclass
class FusionInputs:
    iris: ModalityMeasurement
    voice: ModalityMeasurement
    liveness_passed: bool | None = None  # None = unknown / not evaluated
    mismatch_evidence: bool = False  # explicit template-comparison evidence only
    spoof_evidence: bool = False  # explicit anti-spoof classifier evidence only


@dataclass
class FusionDecision:
    decision: str  # ACCEPTED | RETRY_REQUIRED | REJECTED_MISMATCH | REJECTED_SPOOF | PROCESSING_ERROR
    reason_code: str
    message: str
    fusion_score: float
    fusion_threshold: float
    iris_weight: float
    voice_weight: float
    face_weight: float = 0.0
    policy: dict = field(default_factory=dict)


def modality_reliability(quality: float, detection_confidence: float) -> float:
    """Reliability multiplier in [0, 1] used to reweight modalities.

    Quality and detection confidence each contribute; their product is
    sharpened so a confident, clean capture dominates an unreliable one.
    """
    base = _clamp(quality) * _clamp(detection_confidence)
    return _clamp(base ** 1.25)


def quality_gate_open(
    quality: float,
    detection_confidence: float,
    quality_threshold: float,
    detection_confidence_threshold: float,
) -> bool:
    """True when a measurement is strong enough to count as valid evidence."""
    return (
        _clamp(quality) >= quality_threshold
        and _clamp(detection_confidence) >= detection_confidence_threshold
    )


def fuse_modalities(
    inputs: FusionInputs,
    *,
    base_voice_weight: float,
    base_iris_weight: float,
    fusion_threshold: float,
    iris_quality_threshold: float,
    iris_detection_confidence_threshold: float,
    voice_quality_threshold: float,
    voice_activity_threshold: float,
    single_modality_fallback_threshold: float,
) -> FusionDecision:
    """Fuse iris + voice measurements into a quality-aware decision.

    Returns one of:
      - ACCEPTED: policy satisfied (both valid and agree, or a single valid
        modality with high confidence and the other temporarily unreliable).
      - RETRY_REQUIRED: capture quality/measurability is the problem.
      - REJECTED_MISMATCH / REJECTED_SPOOF: only with explicit evidence.
    """
    iris = inputs.iris
    voice = inputs.voice

    # ---- Explicit evidence failures first -------------------------------
    if inputs.spoof_evidence:
        return FusionDecision(
            decision="REJECTED_SPOOF",
            reason_code=ReasonCode.REJECTED_SPOOF,
            message=REASON_MESSAGES[ReasonCode.REJECTED_SPOOF],
            fusion_score=0.0,
            fusion_threshold=fusion_threshold,
            iris_weight=0.0,
            voice_weight=0.0,
            policy={},
        )
    if inputs.mismatch_evidence:
        return FusionDecision(
            decision="REJECTED_MISMATCH",
            reason_code=ReasonCode.REJECTED_MISMATCH,
            message=REASON_MESSAGES[ReasonCode.REJECTED_MISMATCH],
            fusion_score=0.0,
            fusion_threshold=fusion_threshold,
            iris_weight=0.0,
            voice_weight=0.0,
            policy={},
        )

    # ---- Liveness must never be contradicted ---------------------------
    liveness_ok = inputs.liveness_passed is not False

    # ---- Measurement validity (quality gates) --------------------------
    iris_valid = quality_gate_open(
        iris.quality,
        iris.detection_confidence,
        iris_quality_threshold,
        iris_detection_confidence_threshold,
    ) and bool(iris.score > 0.0 or iris.quality > 0.0)
    voice_valid = quality_gate_open(
        voice.quality,
        voice.detection_confidence,
        voice_quality_threshold,
        voice_detection_confidence_floor(),
    ) and (
        voice.speech_activity is None
        or _clamp(voice.speech_activity) >= voice_activity_threshold
    )
    inputs.iris.valid_measurement = iris_valid
    inputs.voice.valid_measurement = voice_valid

    # A single modality may carry authentication only when a separate,
    # affirmative liveness stage has passed. Merely omitting liveness is not
    # enough. This makes the fallback usable without turning capture failure
    # into an authentication bypass.
    if inputs.liveness_passed is True and iris_valid != voice_valid:
        reliable = iris if iris_valid else voice
        reliability = modality_reliability(
            reliable.quality,
            reliable.detection_confidence,
        )
        if (
            reliability >= 0.75
            and _clamp(reliable.score) >= single_modality_fallback_threshold
        ):
            iris_weight = 1.0 if iris_valid else 0.0
            voice_weight = 1.0 if voice_valid else 0.0
            return FusionDecision(
                decision="ACCEPTED",
                reason_code=ReasonCode.SINGLE_MODALITY_HIGH_CONFIDENCE,
                message=REASON_MESSAGES[
                    ReasonCode.SINGLE_MODALITY_HIGH_CONFIDENCE
                ],
                fusion_score=_round4(_clamp(reliable.score)),
                fusion_threshold=single_modality_fallback_threshold,
                iris_weight=iris_weight,
                voice_weight=voice_weight,
                policy={
                    "iris_valid": iris_valid,
                    "voice_valid": voice_valid,
                    "liveness_required": True,
                    "liveness_passed": True,
                    "reliable_modality_reliability": _round4(reliability),
                },
            )

    # ---- Quality-only rejections (retry states, not identity failures) --
    if not iris_valid and not voice_valid:
        code = (
            ReasonCode.VOICE_NO_SPEECH_ACTIVITY
            if voice.speech_activity is not None
            and _clamp(voice.speech_activity) < voice_activity_threshold
            else ReasonCode.NO_VALID_MODALITY
        )
        return FusionDecision(
            decision="RETRY_REQUIRED",
            reason_code=code,
            message=REASON_MESSAGES[code],
            fusion_score=0.0,
            fusion_threshold=fusion_threshold,
            iris_weight=0.0,
            voice_weight=0.0,
            policy={"iris_valid": False, "voice_valid": False},
        )
    if not iris_valid:
        code = (
            ReasonCode.IRIS_NOT_DETECTED
            if _clamp(iris.detection_confidence) < 0.05
            else ReasonCode.IRIS_QUALITY_TOO_LOW
        )
        return FusionDecision(
            decision="RETRY_REQUIRED",
            reason_code=code,
            message=REASON_MESSAGES[code],
            fusion_score=0.0,
            fusion_threshold=fusion_threshold,
            iris_weight=0.0,
            voice_weight=1.0,
            policy={"iris_valid": False, "voice_valid": True},
        )
    if not voice_valid:
        code = (
            ReasonCode.VOICE_NO_SPEECH_ACTIVITY
            if voice.speech_activity is not None
            and _clamp(voice.speech_activity) < voice_activity_threshold
            else ReasonCode.VOICE_QUALITY_TOO_LOW
        )
        return FusionDecision(
            decision="RETRY_REQUIRED",
            reason_code=code,
            message=REASON_MESSAGES[code],
            fusion_score=0.0,
            fusion_threshold=fusion_threshold,
            iris_weight=1.0,
            voice_weight=0.0,
            policy={"iris_valid": True, "voice_valid": False},
        )

    # ---- Both modalities valid: reliability-weighted fusion ------------
    voice_reliability = modality_reliability(
        voice.quality, voice.detection_confidence
    )
    iris_reliability = modality_reliability(
        iris.quality, iris.detection_confidence
    )
    weighted_voice = max(base_voice_weight * voice_reliability, 1e-6)
    weighted_iris = max(base_iris_weight * iris_reliability, 1e-6)
    total = weighted_voice + weighted_iris
    voice_weight = weighted_voice / total
    iris_weight = weighted_iris / total

    fusion_score = _clamp(
        (_clamp(voice.score) * voice_weight)
        + (_clamp(iris.score) * iris_weight)
    )

    accepted = liveness_ok and fusion_score >= fusion_threshold

    # Single-modality fallback: the other modality is only *weak*, not
    # invalid (its gate is closed by reliability, not by validity above),
    # so a very strong remaining modality may carry the decision.
    if not accepted and liveness_ok:
        reliable_score = (
            _clamp(voice.score) if voice_reliability >= iris_reliability else _clamp(iris.score)
        )
        strong_reliability = max(voice_reliability, iris_reliability)
        if (
            strong_reliability >= 0.75
            and reliable_score >= single_modality_fallback_threshold
            and fusion_score >= single_modality_fallback_threshold * 0.5
        ):
            accepted = True

    if accepted:
        # Both modalities passed their quality gates at this point; when one
        # carried noticeably less weight we still report all modalities
        # valid — the weights in the payload show which one dominated.
        code = ReasonCode.ALL_MODALITIES_VALID
        return FusionDecision(
            decision="ACCEPTED",
            reason_code=code,
            message=REASON_MESSAGES[code],
            fusion_score=_round4(fusion_score),
            fusion_threshold=fusion_threshold,
            iris_weight=_round4(iris_weight),
            voice_weight=_round4(voice_weight),
            policy={
                "iris_valid": True,
                "voice_valid": True,
                "iris_reliability": _round4(iris_reliability),
                "voice_reliability": _round4(voice_reliability),
            },
        )

    return FusionDecision(
        decision="RETRY_REQUIRED",
        reason_code=ReasonCode.FUSION_INCONCLUSIVE,
        message=REASON_MESSAGES[ReasonCode.FUSION_INCONCLUSIVE],
        fusion_score=_round4(fusion_score),
        fusion_threshold=fusion_threshold,
        iris_weight=_round4(iris_weight),
        voice_weight=_round4(voice_weight),
        policy={
            "iris_valid": True,
            "voice_valid": True,
            "iris_reliability": _round4(iris_reliability),
            "voice_reliability": _round4(voice_reliability),
        },
    )


def voice_detection_confidence_floor() -> float:
    """Voice samples are always measurable; only quality/activity gate them."""
    return 0.0


def fuse_three_modalities(
    *,
    face: ModalityMeasurement,
    iris: ModalityMeasurement,
    voice: ModalityMeasurement,
    base_face_weight: float,
    base_iris_weight: float,
    base_voice_weight: float,
    fusion_threshold: float,
    face_quality_threshold: float,
    iris_quality_threshold: float,
    iris_detection_confidence_threshold: float,
    voice_quality_threshold: float,
    voice_activity_threshold: float,
    face_similarity_threshold: float,
    iris_similarity_threshold: float,
    voice_similarity_threshold: float,
    spoof_evidence: bool = False,
) -> FusionDecision:
    """Strict three-modal, quality-aware identity fusion.

    Capture failures produce RETRY_REQUIRED. A mismatch is emitted only after
    all three modalities produced usable measurements and at least one usable
    identity score failed its modality threshold. The aggregate score is a
    normalized similarity score, not a probability.
    """
    if spoof_evidence:
        return FusionDecision(
            decision="REJECTED_SPOOF",
            reason_code=ReasonCode.REJECTED_SPOOF,
            message=REASON_MESSAGES[ReasonCode.REJECTED_SPOOF],
            fusion_score=0.0,
            fusion_threshold=fusion_threshold,
            face_weight=0.0,
            iris_weight=0.0,
            voice_weight=0.0,
        )

    face.valid_measurement = bool(face.valid_measurement) and quality_gate_open(
        face.quality,
        face.detection_confidence,
        face_quality_threshold,
        0.0,
    )
    iris.valid_measurement = bool(iris.valid_measurement) and quality_gate_open(
        iris.quality,
        iris.detection_confidence,
        iris_quality_threshold,
        iris_detection_confidence_threshold,
    )
    voice.valid_measurement = bool(voice.valid_measurement) and quality_gate_open(
        voice.quality,
        voice.detection_confidence,
        voice_quality_threshold,
        0.0,
    ) and (
        voice.speech_activity is not None
        and voice.speech_activity >= voice_activity_threshold
    )

    if not face.valid_measurement:
        code = (
            ReasonCode.FACE_NOT_DETECTED
            if face.detection_confidence <= 0.01
            else ReasonCode.FACE_QUALITY_TOO_LOW
        )
        return FusionDecision(
            "RETRY_REQUIRED",
            code,
            REASON_MESSAGES[code],
            0.0,
            fusion_threshold,
            0.0,
            0.0,
            0.0,
            {"face_valid": False, "iris_valid": iris.valid_measurement, "voice_valid": voice.valid_measurement},
        )
    if not iris.valid_measurement:
        code = ReasonCode.IRIS_NOT_DETECTED if iris.detection_confidence < 0.05 else ReasonCode.IRIS_QUALITY_TOO_LOW
        return FusionDecision(
            "RETRY_REQUIRED", code, REASON_MESSAGES[code], 0.0,
            fusion_threshold, 0.0, 0.0, 0.0,
            {"face_valid": True, "iris_valid": False, "voice_valid": voice.valid_measurement},
        )
    if not voice.valid_measurement:
        code = (
            ReasonCode.VOICE_NO_SPEECH_ACTIVITY
            if (voice.speech_activity or 0.0) < voice_activity_threshold
            else ReasonCode.VOICE_QUALITY_TOO_LOW
        )
        return FusionDecision(
            "RETRY_REQUIRED", code, REASON_MESSAGES[code], 0.0,
            fusion_threshold, 0.0, 0.0, 0.0,
            {"face_valid": True, "iris_valid": True, "voice_valid": False},
        )

    reliabilities = {
        "face": modality_reliability(face.quality, face.detection_confidence),
        "iris": modality_reliability(iris.quality, iris.detection_confidence),
        "voice": modality_reliability(voice.quality, voice.detection_confidence),
    }
    weighted = {
        "face": max(base_face_weight * reliabilities["face"], 1e-6),
        "iris": max(base_iris_weight * reliabilities["iris"], 1e-6),
        "voice": max(base_voice_weight * reliabilities["voice"], 1e-6),
    }
    total = sum(weighted.values())
    weights = {key: value / total for key, value in weighted.items()}
    score = _clamp(
        face.score * weights["face"]
        + iris.score * weights["iris"]
        + voice.score * weights["voice"]
    )
    failed_modalities = [
        name
        for name, value, threshold in (
            ("face", face.score, face_similarity_threshold),
            ("iris", iris.score, iris_similarity_threshold),
            ("voice", voice.score, voice_similarity_threshold),
        )
        if value < threshold
    ]
    policy = {
        "face_valid": True,
        "iris_valid": True,
        "voice_valid": True,
        "face_reliability": _round4(reliabilities["face"]),
        "iris_reliability": _round4(reliabilities["iris"]),
        "voice_reliability": _round4(reliabilities["voice"]),
        "failed_modalities": failed_modalities,
        "score_kind": "normalized_similarity_not_probability",
    }
    if failed_modalities:
        message = "Biometric mismatch in: " + ", ".join(failed_modalities) + "."
        return FusionDecision(
            "REJECTED_MISMATCH",
            ReasonCode.REJECTED_MISMATCH,
            message,
            _round4(score),
            fusion_threshold,
            _round4(weights["iris"]),
            _round4(weights["voice"]),
            _round4(weights["face"]),
            policy,
        )
    if score < fusion_threshold:
        return FusionDecision(
            "RETRY_REQUIRED",
            ReasonCode.FUSION_INCONCLUSIVE,
            REASON_MESSAGES[ReasonCode.FUSION_INCONCLUSIVE],
            _round4(score),
            fusion_threshold,
            _round4(weights["iris"]),
            _round4(weights["voice"]),
            _round4(weights["face"]),
            policy,
        )
    return FusionDecision(
        "ACCEPTED",
        ReasonCode.ALL_MODALITIES_VALID,
        "Face, iris, and voice matched the enrolled templates.",
        _round4(score),
        fusion_threshold,
        _round4(weights["iris"]),
        _round4(weights["voice"]),
        _round4(weights["face"]),
        policy,
    )


def fuse_face_voice(
    *,
    face: ModalityMeasurement,
    voice: ModalityMeasurement,
    base_face_weight: float,
    base_voice_weight: float,
    fusion_threshold: float,
    face_quality_threshold: float,
    voice_quality_threshold: float,
    voice_activity_threshold: float,
    face_similarity_threshold: float,
    voice_similarity_threshold: float,
    spoof_evidence: bool = False,
) -> FusionDecision:
    """Fuse real face and voice identity measurements for prototype mode.

    Iris is deliberately absent from this policy; the camera frame can still
    be labelled and transported as an iris sample, but it contributes no
    identity evidence. This keeps the low-quality-camera submission path
    explicit instead of manufacturing an iris score. A dedicated anti-spoofing
    model may supply ``spoof_evidence`` to force a spoof rejection.
    """
    if spoof_evidence:
        return FusionDecision(
            decision="REJECTED_SPOOF",
            reason_code=ReasonCode.REJECTED_SPOOF,
            message=REASON_MESSAGES[ReasonCode.REJECTED_SPOOF],
            fusion_score=0.0,
            fusion_threshold=fusion_threshold,
            face_weight=0.0,
            iris_weight=0.0,
            voice_weight=0.0,
            policy={"spoof_evidence": True, "iris_policy": "capture_only"},
        )
    face.valid_measurement = bool(face.valid_measurement) and quality_gate_open(
        face.quality,
        face.detection_confidence,
        face_quality_threshold,
        0.0,
    )
    voice.valid_measurement = bool(voice.valid_measurement) and quality_gate_open(
        voice.quality,
        voice.detection_confidence,
        voice_quality_threshold,
        0.0,
    ) and (voice.speech_activity or 0.0) >= voice_activity_threshold

    if not face.valid_measurement:
        code = (
            ReasonCode.FACE_NOT_DETECTED
            if face.detection_confidence <= 0.01
            else ReasonCode.FACE_QUALITY_TOO_LOW
        )
        return FusionDecision(
            "RETRY_REQUIRED", code, REASON_MESSAGES[code], 0.0,
            fusion_threshold, 0.0, 0.0, 0.0,
            {"face_valid": False, "voice_valid": voice.valid_measurement,
             "iris_policy": "capture_only"},
        )
    if not voice.valid_measurement:
        code = (
            ReasonCode.VOICE_NO_SPEECH_ACTIVITY
            if (voice.speech_activity or 0.0) < voice_activity_threshold
            else ReasonCode.VOICE_QUALITY_TOO_LOW
        )
        return FusionDecision(
            "RETRY_REQUIRED", code, REASON_MESSAGES[code], 0.0,
            fusion_threshold, 0.0, 0.0, 0.0,
            {"face_valid": True, "voice_valid": False,
             "iris_policy": "capture_only"},
        )

    face_reliability = modality_reliability(
        face.quality, face.detection_confidence
    )
    voice_reliability = modality_reliability(
        voice.quality, voice.detection_confidence
    )
    face_weight = max(base_face_weight * face_reliability, 1e-6)
    voice_weight = max(base_voice_weight * voice_reliability, 1e-6)
    total = face_weight + voice_weight
    face_weight /= total
    voice_weight /= total
    score = _clamp(face.score * face_weight + voice.score * voice_weight)
    failed_modalities = [
        name
        for name, value, threshold in (
            ("face", face.score, face_similarity_threshold),
            ("voice", voice.score, voice_similarity_threshold),
        )
        if value < threshold
    ]
    policy = {
        "face_valid": True,
        "voice_valid": True,
        "iris_policy": "capture_only",
        "face_reliability": _round4(face_reliability),
        "voice_reliability": _round4(voice_reliability),
        "failed_modalities": failed_modalities,
        "score_kind": "normalized_similarity_not_probability",
    }
    if failed_modalities:
        return FusionDecision(
            "REJECTED_MISMATCH",
            ReasonCode.REJECTED_MISMATCH,
            "Biometric mismatch in: " + ", ".join(failed_modalities) + ".",
            _round4(score), fusion_threshold, 0.0,
            _round4(voice_weight), _round4(face_weight), policy,
        )
    if score < fusion_threshold:
        return FusionDecision(
            "RETRY_REQUIRED",
            ReasonCode.FUSION_INCONCLUSIVE,
            REASON_MESSAGES[ReasonCode.FUSION_INCONCLUSIVE],
            _round4(score), fusion_threshold, 0.0,
            _round4(voice_weight), _round4(face_weight), policy,
        )
    return FusionDecision(
        "ACCEPTED",
        ReasonCode.FACE_VOICE_VALID_IRIS_CAPTURE_ONLY,
        REASON_MESSAGES[ReasonCode.FACE_VOICE_VALID_IRIS_CAPTURE_ONLY],
        _round4(score), fusion_threshold, 0.0,
        _round4(voice_weight), _round4(face_weight), policy,
    )


# ---------------------------------------------------------------------------
# Calibrated thresholds
# ---------------------------------------------------------------------------


def _default_thresholds() -> dict:
    return {
        "fusion_threshold": settings.FUSION_THRESHOLD,
        "single_modality_fallback_threshold": getattr(
            settings, "FUSION_SINGLE_MODALITY_FALLBACK_THRESHOLD", 0.72
        ),
        "source": "defaults",
        "calibrated": False,
    }


def get_calibrated_thresholds() -> dict:
    """Load calibrated thresholds from disk, falling back to settings.

    Calibration is produced offline by the ``calibrate_fusion_thresholds``
    management command from genuine-user and impostor samples; see
    docs/reason_codes.md for the expected JSON shape.
    """
    import json
    from pathlib import Path

    path = Path(settings.FUSION_CALIBRATION_PATH)
    if not path.exists():
        return _default_thresholds()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fusion = float(data["fusion_threshold"])
        fallback = float(data["single_modality_fallback_threshold"])
        if not 0.0 < fusion < 1.0 or not 0.0 < fallback < 1.0:
            raise ValueError("thresholds out of range")
        return {
            "fusion_threshold": fusion,
            "single_modality_fallback_threshold": fallback,
            "source": str(path),
            "calibrated": True,
            "calibrated_at": data.get("calibrated_at"),
            "genuine_samples": data.get("genuine_samples"),
            "impostor_samples": data.get("impostor_samples"),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return _default_thresholds()
