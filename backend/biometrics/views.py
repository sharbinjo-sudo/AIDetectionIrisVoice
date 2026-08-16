from __future__ import annotations

from django.conf import settings
from django.db import connection
from django.db.models import Q
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BiometricUser
from .serializers import (
    BiometricAuthenticateRequestSerializer,
    EnrollmentStatusSerializer,
    IrisTestRequestSerializer,
    UserDetailSerializer,
    UserSerializer,
    VoiceTestRequestSerializer,
)
from .services.exceptions import BiometricServiceError
from .services.workflow import (
    authenticate_human,
    evaluate_iris_test,
    evaluate_voice_test,
    get_service_health,
    resolve_user,
)
from .services.storage import temporary_upload


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
        payload = {
            "status": "ok" if database_ready else "degraded",
            "database": "ready" if database_ready else "unavailable",
            "voice_model": health["voice_model"],
            "iris_model": health["iris_model"],
            "development_thresholds": health["development_thresholds"],
        }
        return success_response(payload)


class SystemConfigurationView(APIView):
    def get(self, request):
        health = get_service_health()
        return success_response(
            {
                "api_prefix": settings.API_PREFIX,
                "privacy_mode": True,
                "retain_processed_uploads": settings.RETAIN_PROCESSED_UPLOADS,
                "development_thresholds": settings.DEVELOPMENT_THRESHOLDS,
                "voice_weight": settings.FUSION_VOICE_WEIGHT,
                "iris_weight": settings.FUSION_IRIS_WEIGHT,
                "voice_threshold": settings.VOICE_QUALITY_THRESHOLD,
                "voice_activity_threshold": settings.VOICE_ACTIVITY_THRESHOLD,
                "iris_threshold": settings.IRIS_QUALITY_THRESHOLD,
                "fusion_threshold": settings.FUSION_THRESHOLD,
                "voice_sample_rate": settings.VOICE_SAMPLE_RATE,
                "voice_min_seconds": settings.VOICE_MIN_SECONDS,
                "voice_max_seconds": settings.VOICE_MAX_SECONDS,
                "minimum_voice_samples": 1,
                "minimum_iris_samples": 1,
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


class BiometricAuthenticateView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        serializer = BiometricAuthenticateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            with temporary_upload(data["iris_file"], prefix="auth_iris_", suffix=".jpg") as iris_path:
                with temporary_upload(
                    data["blink_file"],
                    prefix="auth_blink_",
                    suffix=".jpg",
                ) as blink_path:
                    with temporary_upload(
                        data["voice_file"],
                        prefix="auth_voice_",
                        suffix=".wav",
                    ) as voice_path:
                        result = authenticate_human(
                            open_eye_path=iris_path,
                            blink_path=blink_path,
                            voice_path=voice_path,
                            eye_side=data["eye_side"],
                            challenge_phrase=data.get("challenge_phrase"),
                        )
        except BiometricServiceError as exc:
            return error_response(str(exc), exc.status_code)
        return success_response(result)


class AuthenticationAttemptSaveView(APIView):
    def post(self, request, attempt_id):
        del request, attempt_id
        return error_response(
            "Verification persistence is disabled in privacy mode.",
            status.HTTP_410_GONE,
        )
