from __future__ import annotations

import logging

from django.conf import settings
from django.core import signing
from django.db import connection
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuthenticationAttempt, BankingCustomer, BiometricUser, Decision
from .throttles import PinAddressThrottle, PinCustomerThrottle
from .serializers import (
    BankingCustomerSerializer,
    BankingLoginSerializer,
    BankingRegisterSerializer,
    BiometricAuthenticateRequestSerializer,
    BiometricEnrollmentRequestSerializer,
    EnrollmentStatusSerializer,
    IrisTrackingRequestSerializer,
    IrisTestRequestSerializer,
    UserDetailSerializer,
    UserSerializer,
    VoiceTestRequestSerializer,
)
from .services.exceptions import BiometricServiceError
from .services.workflow import (
    authenticate_enrolled_user,
    enroll_user_biometrics,
    evaluate_iris_test,
    evaluate_voice_test,
    get_service_health,
    resolve_user,
)
from .services.engines import get_iris_engine
from .services.fusion import get_calibrated_thresholds
from .services.storage import temporary_upload, temporary_uploads

logger = logging.getLogger(__name__)


def _require_session_user(request, identifier: str) -> BiometricUser:
    """Resolve a user and ensure the signed banking session belongs to it."""
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise BiometricServiceError("A valid banking session is required.")
    try:
        payload = signing.loads(
            authorization.removeprefix("Bearer ").strip(),
            salt="banking-login",
            max_age=4 * 60 * 60,
        )
    except signing.BadSignature as exc:
        raise BiometricServiceError("The banking session is invalid or expired.") from exc
    user = resolve_user(identifier)
    if str(payload.get("biometric_user_id")) != str(user.id):
        raise BiometricServiceError("The banking session does not match this biometric profile.")
    return user


def success_response(data, response_status=status.HTTP_200_OK) -> Response:
    return Response({"data": data}, status=response_status)


def error_response(message: str, response_status: int) -> Response:
    return Response({"message": message}, status=response_status)


class HealthView(APIView):
    def get(self, request):
        database_ready = True
        try:
            connection.ensure_connection()
        except Exception:
            database_ready = False

        health = get_service_health()
        liveness = health.get("face_liveness_model") or {}
        liveness_ready = bool(liveness.get("ready"))
        liveness_required = bool(liveness.get("required", True))
        # Global readiness reflects the API, database, and the three deployed
        # identity models. A not-yet-provisioned anti-spoofing asset must not
        # make the whole service look like it is still starting; it is reported
        # separately as face_verification_ready below.
        service_ready = (
            database_ready
            and health["voice_model"].get("ready") is True
            and health["iris_model"].get("ready") is True
            and health["face_model"].get("ready") is True
            and (
                health["development_thresholds"]
                or health["fusion_calibration_ready"]
            )
        )
        payload = {
            "status": "ok" if service_ready else "degraded",
            "database": "ready" if database_ready else "unavailable",
            "voice_model": health["voice_model"],
            "iris_model": health["iris_model"],
            "face_model": health["face_model"],
            "face_liveness_model": health.get("face_liveness_model"),
            "face_liveness_ready": liveness_ready,
            "face_liveness_required": liveness_required,
            "face_verification_ready": liveness_ready or not liveness_required,
            "offline_mode": health["offline_mode"],
            "development_thresholds": health["development_thresholds"],
            "fusion_calibration_ready": health["fusion_calibration_ready"],
            "fusion_threshold_source": health["fusion_threshold_source"],
        }
        return success_response(payload)


class SystemConfigurationView(APIView):
    def get(self, request):
        health = get_service_health()
        thresholds = get_calibrated_thresholds()
        return success_response(
            {
                "api_prefix": settings.API_PREFIX,
                "privacy_mode": True,
                "retain_processed_uploads": settings.RETAIN_PROCESSED_UPLOADS,
                "offline_mode": settings.BIOMETRIC_OFFLINE_MODE,
                "development_thresholds": settings.DEVELOPMENT_THRESHOLDS,
                "voice_weight": settings.FUSION_VOICE_WEIGHT,
                "iris_weight": settings.FUSION_IRIS_WEIGHT,
                "face_weight": settings.FUSION_FACE_WEIGHT,
                "face_threshold": settings.FACE_QUALITY_THRESHOLD,
                "voice_threshold": settings.VOICE_QUALITY_THRESHOLD,
                "voice_activity_threshold": settings.VOICE_ACTIVITY_THRESHOLD,
                "iris_threshold": settings.IRIS_QUALITY_THRESHOLD,
                "iris_tracking_stable_confidence": (
                    settings.IRIS_TRACKING_STABLE_CONFIDENCE
                ),
                "fusion_threshold": thresholds["fusion_threshold"],
                "fusion_threshold_source": thresholds.get("source", "defaults"),
                "fusion_calibration_ready": bool(thresholds.get("calibrated")),
                "single_modality_fallback_threshold": thresholds[
                    "single_modality_fallback_threshold"
                ],
                "voice_sample_rate": settings.VOICE_SAMPLE_RATE,
                "voice_min_seconds": settings.VOICE_MIN_SECONDS,
                "voice_max_seconds": settings.VOICE_MAX_SECONDS,
                "minimum_face_samples": settings.MIN_FACE_SAMPLES,
                "minimum_voice_samples": settings.MIN_VOICE_SAMPLES,
                "minimum_voice_segments": settings.MIN_VOICE_SEGMENTS,
                "minimum_iris_samples": settings.MIN_IRIS_SAMPLES,
                "face_model": health["face_model"],
                "face_liveness_model": health.get("face_liveness_model"),
                "face_liveness_required": settings.FACE_LIVENESS_REQUIRED,
                "face_liveness_threshold": settings.FACE_LIVENESS_THRESHOLD,
                "voice_model": health["voice_model"],
                "iris_model": health["iris_model"],
            }
        )


class UserListView(APIView):
    def get(self, request):
        search = request.query_params.get("search", "").strip()
        queryset = BiometricUser.objects.all()
        if search:
            queryset = queryset.filter(
                Q(external_id__icontains=search) | Q(full_name__icontains=search)
            )
        serializer = UserSerializer(queryset[:50], many=True)
        return success_response({"results": serializer.data})


class UserDetailView(APIView):
    def get(self, request, user_id: str):
        try:
            user = resolve_user(user_id)
        except BiometricServiceError as exc:
            return error_response(str(exc), exc.status_code)
        return success_response(UserDetailSerializer(user).data)


class UserEnrollmentStatusView(APIView):
    def get(self, request, user_id: str):
        try:
            user = resolve_user(user_id)
        except BiometricServiceError as exc:
            return error_response(str(exc), exc.status_code)
        return success_response(EnrollmentStatusSerializer(user).data)


class BankingRegisterView(APIView):
    def post(self, request):
        serializer = BankingRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return success_response(
            serializer.create_session_payload(customer),
            status.HTTP_201_CREATED,
        )


class BankingLoginView(APIView):
    throttle_classes = (PinAddressThrottle, PinCustomerThrottle)

    def post(self, request):
        serializer = BankingLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.create_session_payload())


class IrisTestView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        serializer = IrisTestRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            with temporary_upload(data["image_file"], prefix="iris_", suffix=".jpg") as path:
                result = evaluate_iris_test(
                    image_path=path,
                    mode=data["mode"],
                    eye_side=data["eye_side"],
                )
        except BiometricServiceError as exc:
            return error_response(str(exc), exc.status_code)
        return success_response(result)


class IrisTrackingView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        serializer = IrisTrackingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with temporary_upload(
                serializer.validated_data["frame"],
                prefix="iris_tracking_",
                suffix=".jpg",
            ) as path:
                result = get_iris_engine().track_iris(path)
        except BiometricServiceError as exc:
            return error_response(str(exc), exc.status_code)
        return success_response(result)


class VoiceTestView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        serializer = VoiceTestRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            with temporary_upload(
                data["voice_file"],
                prefix="voice_",
                suffix=".wav",
            ) as path:
                result = evaluate_voice_test(
                    audio_path=path,
                    mode=data["mode"],
                )
        except BiometricServiceError as exc:
            return error_response(str(exc), exc.status_code)
        return success_response(result)


class BiometricEnrollmentView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, user_id: str):
        serializer = BiometricEnrollmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = _require_session_user(request, user_id)
            with temporary_uploads(
                data["face_files"], prefix="enroll_face_", suffix=".jpg"
            ) as face_paths:
                with temporary_uploads(
                    data["iris_files"], prefix="enroll_iris_", suffix=".jpg"
                ) as iris_paths:
                    with temporary_uploads(
                        data["voice_files"], prefix="enroll_voice_", suffix=".wav"
                    ) as voice_paths:
                        result = enroll_user_biometrics(
                            user=user,
                            face_paths=face_paths,
                            iris_paths=iris_paths,
                            voice_paths=voice_paths,
                            eye_side=data["eye_side"],
                        )
        except BiometricServiceError as exc:
            return error_response(str(exc), exc.status_code)
        return success_response(result)


class BiometricAuthenticateView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        serializer = BiometricAuthenticateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            user = _require_session_user(request, data["user_id"])
            with temporary_uploads(
                data["face_files"], prefix="auth_face_", suffix=".jpg"
            ) as face_paths:
                with temporary_uploads(
                    data["iris_files"], prefix="auth_iris_", suffix=".jpg"
                ) as iris_paths:
                    with temporary_upload(
                        data["voice_file"],
                        prefix="auth_voice_",
                        suffix=".wav",
                    ) as voice_path:
                        result = authenticate_enrolled_user(
                            user=user,
                            face_paths=face_paths,
                            iris_paths=iris_paths,
                            voice_path=voice_path,
                            eye_side=user.enrolled_eye_side,
                        )
        except BiometricServiceError as exc:
            return error_response(str(exc), exc.status_code)

        self._record_attempt(request, result, user=user)
        if result.get("decision") == Decision.ACCEPTED:
            BankingCustomer.objects.filter(biometric_user=user).update(
                last_login_at=timezone.now()
            )
        return success_response(result)

    def _record_attempt(self, request, result: dict, user=None) -> None:
        """Persist aggregate metrics only (privacy mode: no media, no raw
        embeddings, and the calibration service can re-derive everything it
        needs from these fields)."""
        diagnostics = result.get("diagnostics") or {}
        fusion = result.get("fusion") or {}
        iris = result.get("iris") or {}
        voice = result.get("voice") or {}
        face = result.get("face") or {}
        try:
            AuthenticationAttempt.objects.create(
                user=user or self._attempt_user(request),
                face_raw_score=face.get("raw_score"),
                face_normalized_score=face.get("normalized_score"),
                face_threshold=face.get("threshold"),
                face_quality_score=diagnostics.get("face_quality"),
                face_detection_confidence=diagnostics.get(
                    "face_detection_confidence"
                ),
                face_valid_measurement=bool(
                    diagnostics.get("face_valid_measurement")
                ),
                face_passed=bool(face.get("passed")),
                iris_raw_score=iris.get("raw_score"),
                iris_normalized_score=iris.get("normalized_score"),
                iris_threshold=iris.get("threshold"),
                iris_quality_score=diagnostics.get("iris_quality"),
                iris_detection_confidence=diagnostics.get(
                    "iris_detection_confidence"
                ),
                iris_valid_measurement=bool(
                    diagnostics.get("iris_valid_measurement")
                ),
                iris_passed=bool(diagnostics.get("iris_valid_measurement")),
                voice_raw_score=voice.get("raw_score"),
                voice_normalized_score=voice.get("normalized_score"),
                voice_threshold=voice.get("threshold"),
                voice_quality_score=diagnostics.get("voice_quality"),
                voice_passed=bool(diagnostics.get("voice_valid_measurement")),
                voice_valid_measurement=bool(
                    diagnostics.get("voice_valid_measurement")
                ),
                fusion_voice_weight=fusion.get("voice_weight") or 0.0,
                fusion_iris_weight=fusion.get("iris_weight") or 0.0,
                fusion_face_weight=fusion.get("face_weight") or 0.0,
                fusion_score=diagnostics.get("final_score") or 0.0,
                fusion_threshold=diagnostics.get("threshold") or 0.0,
                fusion_reason_code=result.get("reason_code"),
                decision=result.get("decision"),
                failure_reason=result.get("failure_reason"),
                processing_time_ms=result.get("processing_time_ms", 0),
                saved=False,
                metadata={
                    "ui_state": result.get("ui_state"),
                    "reason_code": result.get("reason_code"),
                    "speech_activity": diagnostics.get("speech_activity"),
                    "iris_policy": diagnostics.get("iris_policy", "verified"),
                    "threshold_source": diagnostics.get("threshold_source"),
                    "verification_status": result.get("verification_status"),
                    "face_similarity": result.get("face_similarity"),
                    "liveness": result.get("liveness"),
                },
            )
        except Exception:
            logger.exception("Could not persist IRL authentication attempt.")

    def _attempt_user(self, request):
        user_id = request.data.get("user_id") or request.data.get("customer_id")
        if not user_id:
            return None
        try:
            return resolve_user(str(user_id))
        except BiometricServiceError:
            return None


class AuthenticationAttemptSaveView(APIView):
    def post(self, request, attempt_id):
        del request, attempt_id
        return error_response(
            "Verification persistence is disabled in privacy mode.",
            status.HTTP_410_GONE,
        )
