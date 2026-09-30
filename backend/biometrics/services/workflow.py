from __future__ import annotations

import logging
from time import perf_counter
from uuid import UUID

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from biometrics.models import BiometricUser
from biometrics.models import Decision

from .engines import get_iris_engine, get_voice_engine
from .face_engine import get_face_engine
from .face_liveness import not_evaluated_result, summarize_liveness
from .exceptions import (
    BiometricServiceError,
    BiometricValidationError,
    EnrollmentIncompleteError,
    ModelUnavailableError,
    SpoofDetectedError,
)
from .fusion import (
    FusionDecision,
    FusionInputs,
    ModalityMeasurement,
    REASON_MESSAGES,
    ReasonCode,
    fuse_modalities,
    fuse_face_voice,
    fuse_three_modalities,
    get_calibrated_thresholds,
)
from .template_crypto import decrypt_template, encrypt_template

logger = logging.getLogger(__name__)


def _liveness_evidence(face_samples: list) -> tuple[dict, str]:
    """Aggregate dedicated anti-spoofing results across captured face frames.

    Returns ``(summary, status)`` where status is one of ``none`` (no single
    face frame), ``unavailable`` (the anti-spoofing model could not run),
    ``spoof`` (a presentation attack was detected), or ``ok`` (live).
    Detection confidence is never used here.
    """
    detected = [sample for sample in face_samples if sample.face_count == 1]
    if not detected:
        return not_evaluated_result().as_dict(), "none"
    results = [sample.liveness for sample in detected if sample.liveness is not None]
    summary = (
        summarize_liveness(results) if results else not_evaluated_result().as_dict()
    )
    if not summary.get("evaluated"):
        return {**summary, "status": "UNAVAILABLE"}, "unavailable"
    return summary, "ok" if summary.get("passed") else "spoof"


def resolve_user(identifier: str) -> BiometricUser:
    filters = Q(external_id=identifier)
    try:
        filters |= Q(id=UUID(str(identifier)))
    except (TypeError, ValueError):
        pass

    user = BiometricUser.objects.filter(filters).first()
    if user is None:
        raise BiometricValidationError("The selected user could not be found.")
    return user


def get_service_health() -> dict:
    face = get_face_engine().health()
    voice = get_voice_engine().health()
    iris = get_iris_engine().health()
    thresholds = get_calibrated_thresholds()
    return {
        "face_model": face,
        "face_liveness_model": face.get("liveness_model"),
        "voice_model": voice,
        "iris_model": iris,
        "offline_mode": settings.BIOMETRIC_OFFLINE_MODE,
        "development_thresholds": settings.DEVELOPMENT_THRESHOLDS,
        "fusion_calibration_ready": bool(thresholds.get("calibrated")),
        "fusion_threshold_source": thresholds.get("source", "defaults"),
    }


def evaluate_voice_test(
    *,
    audio_path: str,
    mode: str,
    user: BiometricUser | None = None,
) -> dict:
    started = perf_counter()
    engine = get_voice_engine()

    if mode == "comparison":
        if user is None:
            raise BiometricValidationError("A user is required for comparison mode.")
        if not user.is_enrolled:
            raise EnrollmentIncompleteError(
                "Enrollment was incomplete for the selected user."
            )
        result = engine.compare(audio_path, reference_embedding=user.voice_embedding)
    else:
        sample = engine.extract_features(audio_path)
        activity_ok = sample.speech_activity_score >= settings.VOICE_ACTIVITY_THRESHOLD
        quality_ok = sample.quality_score >= settings.VOICE_QUALITY_THRESHOLD
        passed = (
            sample.duration_seconds >= settings.VOICE_MIN_SECONDS
            and sample.segment_count >= settings.MIN_VOICE_SEGMENTS
            and activity_ok
            and quality_ok
        )
        if (
            sample.duration_seconds < settings.VOICE_MIN_SECONDS
            or sample.segment_count < settings.MIN_VOICE_SEGMENTS
        ):
            message = (
                f"The recording needs at least {settings.MIN_VOICE_SEGMENTS} "
                "complete voice segments. Speak the full phrase and try again."
            )
            reason_code = ReasonCode.VOICE_QUALITY_TOO_LOW
        elif not activity_ok:
            message = "No clear spoken microphone activity was detected. Speak clearly into the mic and try again."
            reason_code = ReasonCode.VOICE_NO_SPEECH_ACTIVITY
        elif not quality_ok:
            message = "The recording was too quiet or unclear. Speak clearly in a quiet place and try again."
            reason_code = ReasonCode.VOICE_QUALITY_TOO_LOW
        else:
            message = "Microphone activity and voice quality verification passed."
            reason_code = ReasonCode.ALL_MODALITIES_VALID
        result = {
            "voice": {
                "duration_seconds": sample.duration_seconds,
                "quality_score": sample.quality_score,
                "speech_detected": activity_ok,
                "speech_activity_score": sample.speech_activity_score,
                "rms_level": sample.rms_level,
                "peak_level": sample.peak_level,
                "segment_count": sample.segment_count,
                "raw_score": sample.quality_score,
                "normalized_score": sample.quality_score,
                "threshold": settings.VOICE_QUALITY_THRESHOLD,
                "activity_threshold": settings.VOICE_ACTIVITY_THRESHOLD,
                "valid_measurement": passed,
                "reason_code": reason_code,
                "passed": passed,
                "message": message,
            },
            "message": message,
        }

    result["processing_time_ms"] = int((perf_counter() - started) * 1000)
    return result


def evaluate_iris_test(
    *,
    image_path: str,
    mode: str,
    eye_side: str,
    user: BiometricUser | None = None,
) -> dict:
    started = perf_counter()
    engine = get_iris_engine()

    if mode == "comparison":
        if user is None:
            raise BiometricValidationError("A user is required for comparison mode.")
        if not user.is_enrolled:
            raise EnrollmentIncompleteError(
                "Enrollment was incomplete for the selected user."
            )
        result = engine.compare(
            image_path,
            reference_embedding=user.iris_embedding,
            eye_side=eye_side,
        )
    else:
        sample = engine.extract_features(image_path=image_path, eye_side=eye_side)
        quality_ok = sample.quality_score >= settings.IRIS_QUALITY_THRESHOLD
        passed = sample.iris_detected and quality_ok
        if not sample.iris_detected:
            message = "No iris could be measured. Move closer, center your open eye and try again."
            reason_code = ReasonCode.IRIS_NOT_DETECTED
        elif not quality_ok:
            message = "The iris capture is unclear (focus, lighting, distance or position). Improve lighting, move closer and capture again."
            reason_code = ReasonCode.IRIS_QUALITY_TOO_LOW
        else:
            message = "Iris quality verification passed."
            reason_code = ReasonCode.ALL_MODALITIES_VALID
        result = {
            "iris": {
                "iris_detected": sample.iris_detected,
                "quality_score": sample.quality_score,
                "detection_confidence": sample.detection_confidence,
                "raw_score": sample.quality_score,
                "normalized_score": sample.quality_score,
                "threshold": settings.IRIS_QUALITY_THRESHOLD,
                "valid_measurement": passed,
                "reason_code": reason_code,
                "passed": passed,
                "message": message,
            },
            "message": message,
        }

    result["processing_time_ms"] = int((perf_counter() - started) * 1000)
    return result


def enroll_user_biometrics(
    *,
    user: BiometricUser,
    face_paths: list[str],
    iris_paths: list[str],
    voice_paths: list[str],
    eye_side: str,
) -> dict:
    """Create encrypted face/voice templates and retain iris captures.

    In ``FACE_PRIMARY_CAPTURE_MODE`` iris files are transport-compatible
    captures only; no iris identity template is fabricated.
    """
    face_engine = get_face_engine()
    face_samples = [face_engine.extract_features(path) for path in face_paths]
    # Registration requires a dedicated liveness result for every captured
    # frame that produced exactly one face. A missing anti-spoofing model
    # fails closed rather than enrolling on detection confidence alone.
    liveness_summary, liveness_status = _liveness_evidence(face_samples)
    # A positive spoof detection is always honored, even in development.
    if liveness_status == "spoof":
        raise SpoofDetectedError(
            "Liveness check failed during enrollment: a presentation attack "
            "(photo, screen, or mask) was detected. Only a live person may enroll."
        )
    # Only a *missing* anti-spoofing model is downgraded outside production;
    # production requires an affirmative liveness result and fails closed.
    if settings.FACE_LIVENESS_REQUIRED and liveness_status == "unavailable":
        raise ModelUnavailableError(
            "The dedicated face anti-spoofing model is unavailable, so face "
            "enrollment could not complete. Provision the liveness model and retry."
        )
    # In the low-quality-camera prototype the same full frames are retained
    # under the iris upload field for UI/API compatibility, but iris
    # segmentation is not a gate and no iris template is created.
    iris_engine = None if settings.FACE_PRIMARY_CAPTURE_MODE else get_iris_engine()
    iris_samples = (
        [iris_engine.extract_features(path, eye_side=eye_side) for path in iris_paths]
        if iris_engine is not None
        else []
    )
    voice_engine = get_voice_engine()
    voice_samples = [voice_engine.extract_features(path) for path in voice_paths]

    problems: list[str] = []
    valid_faces = [
        sample
        for sample in face_samples
        if sample.valid_measurement
        and (not settings.FACE_LIVENESS_REQUIRED or sample.liveness_passed)
    ]
    valid_irises = [
        sample
        for sample in iris_samples
        if sample.iris_detected
        and sample.detection_confidence
        >= settings.IRIS_DETECTION_CONFIDENCE_THRESHOLD
        and sample.quality_score >= settings.IRIS_QUALITY_THRESHOLD
    ]
    valid_voices = [
        sample
        for sample in voice_samples
        if sample.duration_seconds >= settings.VOICE_MIN_SECONDS
        and sample.segment_count >= settings.MIN_VOICE_SEGMENTS
        and sample.speech_activity_score >= settings.VOICE_ACTIVITY_THRESHOLD
        and sample.quality_score >= settings.VOICE_QUALITY_THRESHOLD
    ]
    if len(valid_faces) < settings.MIN_FACE_SAMPLES:
        reasons = [sample.message for sample in face_samples if not sample.valid_measurement]
        problems.append(
            f"Need {settings.MIN_FACE_SAMPLES} usable camera samples; "
            f"{len(valid_faces)} of {len(face_samples)} passed quality checks. "
            + (" ".join(dict.fromkeys(reasons)) or "Retake the camera samples.")
        )
    if not settings.FACE_PRIMARY_CAPTURE_MODE and len(valid_irises) < settings.MIN_IRIS_SAMPLES:
        problems.append(
            f"Need {settings.MIN_IRIS_SAMPLES} stable iris samples. Move closer, "
            "use clear lighting, and keep the selected eye steady."
        )
    if len(valid_voices) < settings.MIN_VOICE_SAMPLES:
        problems.append(
            f"Need {settings.MIN_VOICE_SAMPLES} usable voice samples. Each recording "
            f"must contain at least {settings.MIN_VOICE_SEGMENTS} clear speech segments "
            "with sufficient duration and capture quality."
        )
    if problems:
        raise BiometricValidationError(" ".join(problems))

    face_template = face_engine.aggregate(valid_faces)
    voice_template = voice_engine.aggregate_samples(valid_voices)
    iris_template = (
        iris_engine.aggregate_samples(valid_irises)
        if iris_engine is not None
        else []
    )
    user.face_template_encrypted = encrypt_template(
        {"version": 1, "algorithm": "buffalo_l_arcface", "vector": face_template}
    )
    user.iris_template_encrypted = (
        encrypt_template(
            {"version": 2, "algorithm": "worldcoin_mask_polar_texture", "vector": iris_template}
        )
        if iris_engine is not None
        else ""
    )
    user.voice_template_encrypted = encrypt_template(
        {"version": 1, "algorithm": "speechbrain_ecapa", "vector": voice_template}
    )
    # Remove plaintext legacy representations once encrypted enrollment is complete.
    user.iris_embedding = []
    user.voice_embedding = []
    user.template_version = 2
    user.face_quality_score = round(
        sum(sample.quality_score for sample in valid_faces) / len(valid_faces), 4
    )
    user.iris_quality_score = (
        round(
            sum(sample.quality_score for sample in valid_irises) / len(valid_irises),
            4,
        )
        if valid_irises
        else None
    )
    user.voice_quality_score = round(
        sum(sample.quality_score for sample in valid_voices) / len(valid_voices), 4
    )
    user.face_sample_count = len(valid_faces)
    user.iris_sample_count = (
        len(iris_paths) if settings.FACE_PRIMARY_CAPTURE_MODE else len(valid_irises)
    )
    user.voice_sample_count = len(valid_voices)
    user.enrolled_eye_side = eye_side
    user.enrollment_status = "COMPLETE"
    user.last_enrolled_at = timezone.now()
    user.save(
        update_fields=[
            "face_template_encrypted",
            "iris_template_encrypted",
            "voice_template_encrypted",
            "template_version",
            "iris_embedding",
            "voice_embedding",
            "face_quality_score",
            "iris_quality_score",
            "voice_quality_score",
            "face_sample_count",
            "iris_sample_count",
            "voice_sample_count",
            "enrolled_eye_side",
            "enrollment_status",
            "last_enrolled_at",
            "updated_at",
        ]
    )
    return {
        "enrollment_status": user.enrollment_status,
        "user_id": str(user.id),
        "eye_side": eye_side,
        "face_quality": user.face_quality_score,
        "face_similarity": None,
        "liveness": liveness_summary,
        "liveness_result": liveness_summary.get("passed"),
        "verification_status": "ENROLLED",
        "failure_reason": None,
        "face_samples": len(valid_faces),
        "iris_quality": user.iris_quality_score,
        "iris_samples": (
            len(iris_paths)
            if settings.FACE_PRIMARY_CAPTURE_MODE
            else len(valid_irises)
        ),
        "iris_detection_confidence": (
            round(
                sum(sample.detection_confidence for sample in valid_irises)
                / len(valid_irises),
                4,
            )
            if valid_irises
            else 0.0
        ),
        "voice_quality": user.voice_quality_score,
        "speech_activity": round(
            sum(sample.speech_activity_score for sample in valid_voices)
            / len(valid_voices),
            4,
        ),
        "voice_samples": len(valid_voices),
        "voice_segments": sum(sample.segment_count for sample in valid_voices),
        "message": (
            "Face and voice templates were enrolled from multiple samples; iris frames were captured for the prototype."
            if settings.FACE_PRIMARY_CAPTURE_MODE
            else "Face, iris, and voice templates were enrolled successfully."
        ),
    }


def authenticate_enrolled_user(
    *,
    user: BiometricUser,
    face_paths: list[str],
    iris_paths: list[str],
    voice_path: str,
    eye_side: str,
) -> dict:
    """Temporally compare enrolled modalities using the active capture policy."""
    started = perf_counter()
    if not user.is_enrolled:
        raise EnrollmentIncompleteError("Three-modal enrollment is incomplete.")

    face_reference = decrypt_template(user.face_template_encrypted)["vector"]
    iris_reference = (
        decrypt_template(user.iris_template_encrypted)["vector"]
        if user.iris_template_encrypted
        else user.iris_embedding
    )
    voice_reference = (
        decrypt_template(user.voice_template_encrypted)["vector"]
        if user.voice_template_encrypted
        else user.voice_embedding
    )
    face_engine = get_face_engine()
    # Registration uses several samples to build a robust template. Login is
    # a live authentication event, so one validated camera sample is enough;
    # the same quality gates and template comparison still apply.
    auth_face_samples = max(1, settings.AUTH_FACE_SAMPLES)
    auth_iris_samples = max(1, settings.AUTH_IRIS_SAMPLES)
    face_samples = [face_engine.extract_features(path) for path in face_paths]
    # Dedicated anti-spoofing evidence for this live login capture. Detection
    # confidence is never substituted for it; when it is required and missing
    # the authentication fails closed below.
    liveness_summary, liveness_status = _liveness_evidence(face_samples)
    liveness_required = settings.FACE_LIVENESS_REQUIRED
    liveness_spoof = liveness_status == "spoof"
    liveness_unavailable = liveness_required and liveness_status == "unavailable"
    iris_engine = None if settings.FACE_PRIMARY_CAPTURE_MODE else get_iris_engine()
    iris_samples = (
        [iris_engine.extract_features(path, eye_side=eye_side) for path in iris_paths]
        if iris_engine is not None
        else []
    )
    face_data = face_engine.compare_samples(
        face_samples,
        face_reference,
        minimum_samples=auth_face_samples,
    )["face"]
    iris_data = (
        iris_engine.compare_samples(
            iris_samples,
            iris_reference,
            minimum_samples=auth_iris_samples,
        )["iris"]
        if iris_engine is not None and iris_reference
        else {
            "iris_detected": False,
            "quality_score": 0.0,
            "detection_confidence": 0.0,
            "raw_score": None,
            "normalized_score": None,
            "valid_measurement": False,
            "passed": False,
            "sample_count": len(iris_paths),
            "message": "Iris frames were captured; iris identity comparison is disabled in prototype mode.",
        }
    )
    voice_data = get_voice_engine().compare(voice_path, voice_reference)["voice"]

    face_quality = float(face_data.get("quality_score") or 0.0)
    iris_quality = float(iris_data.get("quality_score") or 0.0)
    voice_quality = float(voice_data.get("quality_score") or 0.0)
    speech_activity = float(voice_data.get("speech_activity_score") or 0.0)
    face_score = float(face_data.get("normalized_score") or 0.0)
    iris_score = float(iris_data.get("normalized_score") or 0.0)
    voice_score = float(voice_data.get("normalized_score") or 0.0)
    iris_detected = bool(iris_data.get("iris_detected", False))
    face_detection_confidence = float(
        face_data.get("detection_confidence") or 0.0
    )
    iris_detection_confidence = float(
        iris_data.get("detection_confidence") or (1.0 if iris_detected else 0.0)
    )
    face_valid = bool(face_data.get("valid_measurement", False))
    iris_valid = (
        iris_detected
        and iris_quality >= settings.IRIS_QUALITY_THRESHOLD
        and iris_detection_confidence
        >= settings.IRIS_DETECTION_CONFIDENCE_THRESHOLD
    )
    voice_valid = (
        voice_quality >= settings.VOICE_QUALITY_THRESHOLD
        and speech_activity >= settings.VOICE_ACTIVITY_THRESHOLD
        and int(voice_data.get("segment_count") or 0) >= settings.MIN_VOICE_SEGMENTS
    )
    thresholds = get_calibrated_thresholds()
    face_quality_threshold = settings.FACE_QUALITY_THRESHOLD
    if settings.FACE_PRIMARY_CAPTURE_MODE:
        face_quality_threshold = min(face_quality_threshold, 0.45)
    if not settings.DEVELOPMENT_THRESHOLDS and not thresholds.get("calibrated"):
        raise BiometricValidationError(
            "Production biometric authentication requires a fusion calibration "
            "file derived from genuine-user and impostor samples."
        )
    face_measurement = ModalityMeasurement(
        score=face_score,
        quality=face_quality,
        detection_confidence=face_detection_confidence,
        valid_measurement=face_valid,
    )
    iris_measurement = ModalityMeasurement(
        score=iris_score,
        quality=iris_quality,
        detection_confidence=iris_detection_confidence,
        valid_measurement=iris_valid,
    )
    voice_measurement = ModalityMeasurement(
        score=voice_score,
        quality=voice_quality,
        detection_confidence=1.0,
        valid_measurement=voice_valid,
        speech_activity=speech_activity,
    )
    if liveness_unavailable:
        # Fail closed: without confirmed liveness the face cannot be accepted,
        # and the failure is infrastructural, not a quality or identity result.
        decision = FusionDecision(
            decision=Decision.PROCESSING_ERROR,
            reason_code=ReasonCode.PROCESSING_ERROR,
            message=(
                "The dedicated face anti-spoofing model is unavailable, so "
                "liveness could not be evaluated and verification did not complete."
            ),
            fusion_score=0.0,
            fusion_threshold=thresholds["fusion_threshold"],
            iris_weight=0.0,
            voice_weight=0.0,
            face_weight=0.0,
            policy={"liveness": liveness_summary},
        )
    elif settings.FACE_PRIMARY_CAPTURE_MODE:
        decision = fuse_face_voice(
            face=face_measurement,
            voice=voice_measurement,
            base_face_weight=settings.FUSION_FACE_WEIGHT,
            base_voice_weight=settings.FUSION_VOICE_WEIGHT,
            fusion_threshold=thresholds["fusion_threshold"],
            face_quality_threshold=face_quality_threshold,
            voice_quality_threshold=settings.VOICE_QUALITY_THRESHOLD,
            voice_activity_threshold=settings.VOICE_ACTIVITY_THRESHOLD,
            face_similarity_threshold=settings.FACE_SIMILARITY_THRESHOLD,
            voice_similarity_threshold=settings.VOICE_SIMILARITY_THRESHOLD,
            spoof_evidence=liveness_spoof,
        )
    else:
        decision = fuse_three_modalities(
            face=face_measurement,
            iris=iris_measurement,
            voice=voice_measurement,
            base_face_weight=settings.FUSION_FACE_WEIGHT,
            base_voice_weight=settings.FUSION_VOICE_WEIGHT,
            base_iris_weight=settings.FUSION_IRIS_WEIGHT,
            fusion_threshold=thresholds["fusion_threshold"],
            face_quality_threshold=settings.FACE_QUALITY_THRESHOLD,
            iris_quality_threshold=settings.IRIS_QUALITY_THRESHOLD,
            iris_detection_confidence_threshold=settings.IRIS_DETECTION_CONFIDENCE_THRESHOLD,
            voice_quality_threshold=settings.VOICE_QUALITY_THRESHOLD,
            voice_activity_threshold=settings.VOICE_ACTIVITY_THRESHOLD,
            face_similarity_threshold=settings.FACE_SIMILARITY_THRESHOLD,
            iris_similarity_threshold=settings.IRIS_SIMILARITY_THRESHOLD,
            voice_similarity_threshold=settings.VOICE_SIMILARITY_THRESHOLD,
            spoof_evidence=liveness_spoof,
        )
    decision_enum = Decision(decision.decision)
    accepted = decision_enum == Decision.ACCEPTED
    ui_state = _ui_state_for(decision_enum, decision.reason_code)
    diagnostics = {
        "score_kind": "normalized_template_cosine_similarity_not_calibrated_probability",
        "face_similarity": round(face_score, 4),
        "liveness_status": liveness_summary.get("status"),
        "liveness_passed": liveness_summary.get("passed"),
        "liveness_evaluated": liveness_summary.get("evaluated"),
        "liveness_score": liveness_summary.get("live_score"),
        "liveness_threshold": liveness_summary.get("threshold"),
        "anti_spoof_model": liveness_summary.get("anti_spoof_model"),
        "liveness_required": liveness_required,
        "face_quality": round(face_quality, 4),
        "face_detection_confidence": round(face_detection_confidence, 4),
        "face_valid_measurement": face_measurement.valid_measurement,
        "voice_similarity": round(voice_score, 4),
        "voice_quality": round(voice_quality, 4),
        "speech_activity": round(speech_activity, 4),
        "iris_similarity": round(iris_score, 4),
        "iris_quality": round(iris_quality, 4),
        "iris_detected": iris_detected,
        "iris_detection_confidence": iris_measurement.detection_confidence,
        "iris_valid_measurement": iris_measurement.valid_measurement,
        "iris_policy": "capture_only" if settings.FACE_PRIMARY_CAPTURE_MODE else "verified",
        "voice_valid_measurement": voice_measurement.valid_measurement,
        "effective_voice_weight": decision.voice_weight,
        "effective_iris_weight": decision.iris_weight,
        "effective_face_weight": decision.face_weight,
        "final_score": decision.fusion_score,
        "threshold": decision.fusion_threshold,
        "threshold_source": thresholds.get("source", "defaults"),
        "accepted": accepted,
        "reason_code": decision.reason_code,
    }
    logger.info("Three-modal biometric diagnostic for %s: %s", user.external_id, diagnostics)
    return {
        "face": {
            **face_data,
            "quality_threshold": face_quality_threshold,
            "similarity_score": round(face_score, 4),
            "valid_measurement": face_measurement.valid_measurement,
        },
        "voice": {
            **voice_data,
            "quality_threshold": settings.VOICE_QUALITY_THRESHOLD,
            "similarity_score": round(voice_score, 4),
            "valid_measurement": voice_measurement.valid_measurement,
        },
        "iris": {
            **iris_data,
            "quality_threshold": settings.IRIS_QUALITY_THRESHOLD,
            "similarity_score": round(iris_score, 4),
            "detection_confidence": iris_measurement.detection_confidence,
            "valid_measurement": iris_measurement.valid_measurement,
        },
        "fusion": {
            "face_weight": decision.face_weight,
            "voice_weight": decision.voice_weight,
            "iris_weight": decision.iris_weight,
            "face_normalized_score": round(face_score, 4),
            "voice_normalized_score": round(voice_score, 4),
            "iris_normalized_score": round(iris_score, 4),
            "score": decision.fusion_score,
            "threshold": decision.fusion_threshold,
            "reason_code": decision.reason_code,
            "policy": decision.policy,
        },
        "decision": decision_enum,
        "reason_code": decision.reason_code,
        "reason_message": decision.message,
        "ui_state": ui_state,
        "verification_status": ui_state,
        "face_similarity": round(face_score, 4),
        "liveness": liveness_summary,
        "liveness_result": liveness_summary.get("passed"),
        "failure_reason": None if accepted else decision.message,
        "processing_time_ms": int((perf_counter() - started) * 1000),
        "privacy_mode": True,
        "diagnostics": diagnostics,
    }


def _ui_state_for(decision: str, reason_code: str) -> str:
    """Map a backend decision onto the UI's explicit verification states."""
    if decision == Decision.ACCEPTED:
        return "VERIFIED"
    if decision == Decision.REJECTED_SPOOF:
        return "REJECTED_SPOOF"
    if decision == Decision.REJECTED_MISMATCH:
        return "REJECTED_MISMATCH"
    if decision == Decision.RETRY_REQUIRED:
        quality_reasons = {
            ReasonCode.FACE_NOT_DETECTED,
            ReasonCode.FACE_QUALITY_TOO_LOW,
            ReasonCode.MULTIPLE_FACES,
            ReasonCode.IRIS_NOT_DETECTED,
            ReasonCode.IRIS_QUALITY_TOO_LOW,
            ReasonCode.VOICE_QUALITY_TOO_LOW,
            ReasonCode.VOICE_NO_SPEECH_ACTIVITY,
        }
        return "QUALITY_TOO_LOW" if reason_code in quality_reasons else "RETRY_REQUIRED"
    return "PROCESSING_ERROR"


def authenticate_human(
    *,
    open_eye_path: str,
    voice_path: str,
    eye_side: str,
    challenge_phrase: str | None = None,
    liveness_passed: bool | None = None,
    mismatch_evidence: bool = False,
    spoof_evidence: bool = False,
) -> dict:
    """Quality-aware multimodal human verification (template-free IRL flow).

    This endpoint has NO enrolled reference template, so it has no evidence
    for an impostor-mismatch decision: insufficient capture quality is
    reported as RETRY_REQUIRED / QUALITY_TOO_LOW, never as a rejection.
    REJECTED_* states are reserved for explicit mismatch/spoof evidence,
    which future template-comparison or liveness-classifier flows can pass
    in via ``mismatch_evidence`` / ``spoof_evidence``.
    """
    del challenge_phrase  # Challenge-response phrasing is enforced client-side.
    started = perf_counter()

    try:
        iris_result = evaluate_iris_test(
            image_path=open_eye_path,
            mode="quality_only",
            eye_side=eye_side,
        )
        voice_result = evaluate_voice_test(
            audio_path=voice_path,
            mode="quality_only",
        )
    except BiometricServiceError:
        # Engine failures are infrastructure problems, not user evidence.
        processing_time_ms = int((perf_counter() - started) * 1000)
        logger.exception("IRL biometric processing error")
        return {
            "voice": None,
            "iris": None,
            "fusion": None,
            "decision": Decision.PROCESSING_ERROR,
            "reason_code": ReasonCode.PROCESSING_ERROR,
            "reason_message": REASON_MESSAGES[ReasonCode.PROCESSING_ERROR],
            "ui_state": "PROCESSING_ERROR",
            "failure_reason": REASON_MESSAGES[ReasonCode.PROCESSING_ERROR],
            "processing_time_ms": processing_time_ms,
            "privacy_mode": True,
            "diagnostics": {
                "score_kind": "capture_quality_not_calibrated_similarity"
            },
        }

    iris_data = iris_result["iris"]
    voice_data = voice_result["voice"]

    # These are capture-quality measurements, not calibrated biometric-match
    # probabilities: with no enrolled template there is no similarity score.
    voice_quality = float(voice_data.get("quality_score") or 0.0)
    iris_quality = float(iris_data.get("quality_score") or 0.0)
    speech_activity = float(voice_data.get("speech_activity_score") or 0.0)
    iris_detected = bool(iris_data.get("iris_detected", False))

    iris_inputs = ModalityMeasurement(
        score=iris_quality,
        quality=iris_quality,
        # The still-image path has no graded segmentation confidence; the
        # boolean detection result gates validity and the quality gate does
        # the rest. (The live tracking endpoint exposes graded confidence.)
        detection_confidence=1.0 if iris_detected else 0.0,
        valid_measurement=False,
    )
    voice_inputs = ModalityMeasurement(
        score=voice_quality,
        quality=voice_quality,
        # Voice is always measurable once decoded; quality and speech
        # activity carry the gating.
        detection_confidence=1.0,
        valid_measurement=False,
        speech_activity=speech_activity,
    )

    thresholds = get_calibrated_thresholds()
    try:
        decision = fuse_modalities(
            FusionInputs(
                iris=iris_inputs,
                voice=voice_inputs,
                liveness_passed=liveness_passed,
                mismatch_evidence=mismatch_evidence,
                spoof_evidence=spoof_evidence,
            ),
            base_voice_weight=settings.FUSION_VOICE_WEIGHT,
            base_iris_weight=settings.FUSION_IRIS_WEIGHT,
            fusion_threshold=thresholds["fusion_threshold"],
            iris_quality_threshold=settings.IRIS_QUALITY_THRESHOLD,
            iris_detection_confidence_threshold=(
                settings.IRIS_DETECTION_CONFIDENCE_THRESHOLD
            ),
            voice_quality_threshold=settings.VOICE_QUALITY_THRESHOLD,
            voice_activity_threshold=settings.VOICE_ACTIVITY_THRESHOLD,
            single_modality_fallback_threshold=thresholds[
                "single_modality_fallback_threshold"
            ],
        )
    except Exception:
        processing_time_ms = int((perf_counter() - started) * 1000)
        logger.exception("IRL fusion decision failed")
        return {
            "voice": None,
            "iris": None,
            "fusion": None,
            "decision": Decision.PROCESSING_ERROR,
            "reason_code": ReasonCode.PROCESSING_ERROR,
            "reason_message": REASON_MESSAGES[ReasonCode.PROCESSING_ERROR],
            "ui_state": "PROCESSING_ERROR",
            "failure_reason": REASON_MESSAGES[ReasonCode.PROCESSING_ERROR],
            "processing_time_ms": processing_time_ms,
            "privacy_mode": True,
            "diagnostics": {
                "score_kind": "capture_quality_not_calibrated_similarity"
            },
        }

    decision_enum = Decision(decision.decision)
    accepted = decision_enum == Decision.ACCEPTED
    processing_time_ms = int((perf_counter() - started) * 1000)

    diagnostics = {
        "score_kind": "capture_quality_not_calibrated_similarity",
        "voice_similarity": None,
        "voice_quality": round(voice_quality, 4),
        "speech_activity": round(speech_activity, 4),
        "iris_similarity": None,
        "iris_quality": round(iris_quality, 4),
        "iris_detected": iris_detected,
        "iris_detection_confidence": iris_inputs.detection_confidence,
        "iris_valid_measurement": iris_inputs.valid_measurement,
        "voice_valid_measurement": voice_inputs.valid_measurement,
        "effective_voice_weight": decision.voice_weight,
        "effective_iris_weight": decision.iris_weight,
        "final_score": decision.fusion_score,
        "threshold": decision.fusion_threshold,
        "single_modality_fallback_threshold": thresholds[
            "single_modality_fallback_threshold"
        ],
        "threshold_source": thresholds.get("source", "defaults"),
        "accepted": accepted,
        "reason_code": decision.reason_code,
    }
    logger.info("IRL biometric diagnostic: %s", diagnostics)

    # failure_reason is populated for rejections AND retries: it explains the
    # outcome. Clients must branch on `decision`/`ui_state`, not on the
    # presence of a message, when choosing the failure UI.
    return {
        "voice": {
            "raw_score": voice_data["raw_score"],
            "normalized_score": voice_data["normalized_score"],
            "threshold": voice_data["threshold"],
            "activity_threshold": voice_data.get(
                "activity_threshold", settings.VOICE_ACTIVITY_THRESHOLD
            ),
            "speech_activity_score": voice_data.get("speech_activity_score"),
            "speech_detected": voice_data.get("speech_detected", False),
            "passed": voice_data["passed"],
            "quality_score": voice_data["quality_score"],
            "valid_measurement": voice_inputs.valid_measurement,
            "reason_code": (
                ReasonCode.ALL_MODALITIES_VALID
                if voice_inputs.valid_measurement
                else (
                    ReasonCode.VOICE_NO_SPEECH_ACTIVITY
                    if speech_activity < settings.VOICE_ACTIVITY_THRESHOLD
                    else ReasonCode.VOICE_QUALITY_TOO_LOW
                )
            ),
            "similarity_score": None,
        },
        "iris": {
            "raw_score": iris_data["raw_score"],
            "normalized_score": iris_data["normalized_score"],
            "threshold": iris_data["threshold"],
            "passed": iris_data["passed"],
            "quality_score": iris_data["quality_score"],
            "iris_detected": iris_detected,
            "detection_confidence": iris_inputs.detection_confidence,
            "valid_measurement": iris_inputs.valid_measurement,
            "reason_code": (
                ReasonCode.ALL_MODALITIES_VALID
                if iris_inputs.valid_measurement
                else (
                    ReasonCode.IRIS_NOT_DETECTED
                    if not iris_detected
                    else ReasonCode.IRIS_QUALITY_TOO_LOW
                )
            ),
            "similarity_score": None,
        },
        "fusion": {
            "voice_weight": decision.voice_weight,
            "iris_weight": decision.iris_weight,
            "voice_normalized_score": round(voice_quality, 4),
            "iris_normalized_score": round(iris_quality, 4),
            "score": decision.fusion_score,
            "threshold": decision.fusion_threshold,
            "reason_code": decision.reason_code,
            "policy": decision.policy,
        },
        "decision": decision_enum,
        "reason_code": decision.reason_code,
        "reason_message": decision.message,
        "ui_state": _ui_state_for(decision_enum, decision.reason_code),
        "failure_reason": None if accepted else decision.message,
        "processing_time_ms": processing_time_ms,
        "privacy_mode": True,
        "liveness_evidence": (
            "speech_activity_only"
            if liveness_passed is None
            else "provided_by_caller"
        ),
        "diagnostics": diagnostics,
    }
