from __future__ import annotations

from time import perf_counter
from uuid import UUID

from django.conf import settings
from django.db.models import Q

from biometrics.models import BiometricUser
from biometrics.models import Decision

from .engines import get_iris_engine, get_voice_engine
from .exceptions import (
    BiometricValidationError,
    EnrollmentIncompleteError,
)


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
    voice = get_voice_engine().health()
    iris = get_iris_engine().health()
    return {
        "voice_model": voice,
        "iris_model": iris,
        "development_thresholds": settings.DEVELOPMENT_THRESHOLDS,
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
        passed = (
            sample.duration_seconds >= settings.VOICE_MIN_SECONDS
            and activity_ok
            and sample.quality_score >= settings.VOICE_QUALITY_THRESHOLD
        )
        if sample.duration_seconds < settings.VOICE_MIN_SECONDS:
            message = "The recording was too quiet or too short. Speak clearly and try again."
        elif not activity_ok:
            message = "No clear spoken microphone activity was detected. Speak clearly into the mic and try again."
        elif sample.quality_score < settings.VOICE_QUALITY_THRESHOLD:
            message = "The recording was too quiet or too short. Speak clearly and try again."
        else:
            message = "Microphone activity and voice quality verification passed."
        result = {
            "voice": {
                "duration_seconds": sample.duration_seconds,
                "quality_score": sample.quality_score,
                "speech_detected": activity_ok,
                "speech_activity_score": sample.speech_activity_score,
                "rms_level": sample.rms_level,
                "peak_level": sample.peak_level,
                "raw_score": sample.quality_score,
                "normalized_score": sample.quality_score,
                "threshold": settings.VOICE_QUALITY_THRESHOLD,
                "activity_threshold": settings.VOICE_ACTIVITY_THRESHOLD,
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
        passed = sample.iris_detected and (
            sample.quality_score >= settings.IRIS_QUALITY_THRESHOLD
        )
        message = (
            "Iris quality verification passed."
            if passed
            else "The iris could not be processed. Move closer, improve the lighting and try again."
        )
        result = {
            "iris": {
                "iris_detected": sample.iris_detected,
                "quality_score": sample.quality_score,
                "raw_score": sample.quality_score,
                "normalized_score": sample.quality_score,
                "threshold": settings.IRIS_QUALITY_THRESHOLD,
                "passed": passed,
                "message": message,
            },
            "message": message,
        }

    result["processing_time_ms"] = int((perf_counter() - started) * 1000)
    return result


def authenticate_human(
    *,
    open_eye_path: str,
    blink_path: str,
    voice_path: str,
    eye_side: str,
    challenge_phrase: str | None = None,
) -> dict:
    del challenge_phrase
    started = perf_counter()
    iris_result = get_iris_engine().evaluate_blink(
        open_image_path=open_eye_path,
        blink_image_path=blink_path,
        eye_side=eye_side,
    )
    voice_result = evaluate_voice_test(
        audio_path=voice_path,
        mode="quality_only",
    )

    iris_data = iris_result["iris"]
    voice_data = voice_result["voice"]

    voice_score = float(voice_data["normalized_score"] or 0.0)
    iris_score = float(iris_data["normalized_score"] or 0.0)
    fusion_score = (
        (voice_score * settings.FUSION_VOICE_WEIGHT)
        + (iris_score * settings.FUSION_IRIS_WEIGHT)
    )
    accepted = (
        voice_data["passed"]
        and iris_data["passed"]
        and fusion_score >= settings.FUSION_THRESHOLD
    )

    failure_reason = None
    if not iris_data["passed"]:
        failure_reason = iris_data["message"]
    elif not voice_data["passed"]:
        failure_reason = voice_data["message"]
    elif not accepted:
        failure_reason = (
            "The combined blink and speech challenge score did not meet the verification threshold."
        )

    processing_time_ms = int((perf_counter() - started) * 1000)

    return {
        "voice": {
            "raw_score": voice_data["raw_score"],
            "normalized_score": voice_data["normalized_score"],
            "threshold": voice_data["threshold"],
            "activity_threshold": voice_data.get("activity_threshold", settings.VOICE_ACTIVITY_THRESHOLD),
            "speech_activity_score": voice_data.get("speech_activity_score"),
            "speech_detected": voice_data.get("speech_detected", False),
            "passed": voice_data["passed"],
            "quality_score": voice_data["quality_score"],
        },
        "iris": {
            "raw_score": iris_data["raw_score"],
            "normalized_score": iris_data["normalized_score"],
            "threshold": iris_data["threshold"],
            "passed": iris_data["passed"],
            "quality_score": iris_data["quality_score"],
        },
        "fusion": {
            "voice_weight": settings.FUSION_VOICE_WEIGHT,
            "iris_weight": settings.FUSION_IRIS_WEIGHT,
            "score": round(fusion_score, 4),
            "threshold": settings.FUSION_THRESHOLD,
        },
        "decision": Decision.ACCEPTED if accepted else Decision.REJECTED,
        "failure_reason": failure_reason,
        "processing_time_ms": processing_time_ms,
        "privacy_mode": True,
    }


