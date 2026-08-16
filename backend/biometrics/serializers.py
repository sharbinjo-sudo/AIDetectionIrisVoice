from __future__ import annotations

from rest_framework import serializers

from .models import AuthenticationAttempt, BiometricUser


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = BiometricUser
        fields = ("id", "external_id", "full_name", "enrollment_status")


class UserDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = BiometricUser
        fields = (
            "id",
            "external_id",
            "full_name",
            "enrollment_status",
            "enrolled_eye_side",
            "iris_quality_score",
            "voice_quality_score",
            "last_enrolled_at",
            "created_at",
            "updated_at",
        )


class EnrollmentStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = BiometricUser
        fields = ("id", "external_id", "enrollment_status", "enrolled_eye_side")


class IrisTestRequestSerializer(serializers.Serializer):
    image_file = serializers.FileField()
    eye_side = serializers.ChoiceField(choices=["LEFT", "RIGHT"], default="LEFT")
    mode = serializers.ChoiceField(choices=["quality_only"], default="quality_only")


class VoiceTestRequestSerializer(serializers.Serializer):
    voice_file = serializers.FileField()
    mode = serializers.ChoiceField(choices=["quality_only"], default="quality_only")


class BiometricAuthenticateRequestSerializer(serializers.Serializer):
    iris_file = serializers.FileField()
    blink_file = serializers.FileField()
    voice_file = serializers.FileField()
    eye_side = serializers.ChoiceField(choices=["LEFT", "RIGHT"], default="LEFT")
    challenge_phrase = serializers.CharField(required=False, allow_blank=True)


class AuthenticationAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthenticationAttempt
        fields = ("id", "saved", "saved_at", "decision", "processing_time_ms")
