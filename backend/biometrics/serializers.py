from __future__ import annotations

import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import AuthenticationAttempt, BankingCustomer, BiometricUser
from .services.registration_export import append_registration


def _validate_upload(upload, *, maximum_bytes: int, label: str):
    size = int(getattr(upload, "size", 0) or 0)
    if size <= 0:
        raise serializers.ValidationError(f"The {label} file is empty.")
    if size > maximum_bytes:
        maximum_mb = maximum_bytes / (1024 * 1024)
        raise serializers.ValidationError(
            f"The {label} file is too large. Maximum size is {maximum_mb:g} MB."
        )
    return upload


def validate_iris_upload(upload):
    return _validate_upload(
        upload,
        maximum_bytes=settings.MAX_IRIS_UPLOAD_BYTES,
        label="iris image",
    )


def validate_voice_upload(upload):
    return _validate_upload(
        upload,
        maximum_bytes=settings.MAX_VOICE_UPLOAD_BYTES,
        label="voice recording",
    )


def validate_face_upload(upload):
    return _validate_upload(
        upload,
        maximum_bytes=settings.MAX_FACE_UPLOAD_BYTES,
        label="face image",
    )


def _upload_list(validator, *, minimum: int):
    return serializers.ListField(
        child=serializers.FileField(validators=[validator]),
        min_length=minimum,
        max_length=max(minimum, 8),
        allow_empty=False,
    )


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
            "face_quality_score",
            "iris_quality_score",
            "voice_quality_score",
            "face_sample_count",
            "iris_sample_count",
            "voice_sample_count",
            "last_enrolled_at",
            "created_at",
            "updated_at",
        )


class EnrollmentStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = BiometricUser
        fields = ("id", "external_id", "enrollment_status", "enrolled_eye_side")


class IrisTestRequestSerializer(serializers.Serializer):
    image_file = serializers.FileField(validators=[validate_iris_upload])
    eye_side = serializers.ChoiceField(choices=["LEFT", "RIGHT"], default="LEFT")
    mode = serializers.ChoiceField(choices=["quality_only"], default="quality_only")


class IrisTrackingRequestSerializer(serializers.Serializer):
    frame = serializers.FileField(
        validators=[
            lambda upload: _validate_upload(
                upload,
                maximum_bytes=settings.MAX_TRACKING_FRAME_BYTES,
                label="tracking frame",
            )
        ]
    )


def _validate_challenge_frame(upload):
    return _validate_upload(
        upload,
        maximum_bytes=settings.MAX_TRACKING_FRAME_BYTES,
        label="challenge frame",
    )


class LivenessChallengeVerifyRequestSerializer(serializers.Serializer):
    challenge_id = serializers.CharField(max_length=64)
    frames = serializers.ListField(
        child=serializers.FileField(validators=[_validate_challenge_frame]),
        min_length=settings.FACE_CHALLENGE_MIN_FRAMES,
        max_length=settings.FACE_CHALLENGE_MAX_FRAMES,
        allow_empty=False,
    )


class VoiceTestRequestSerializer(serializers.Serializer):
    voice_file = serializers.FileField(validators=[validate_voice_upload])
    mode = serializers.ChoiceField(choices=["quality_only"], default="quality_only")


class BiometricAuthenticateRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=64)
    face_files = _upload_list(
        validate_face_upload,
        minimum=settings.AUTH_FACE_SAMPLES,
    )
    iris_files = _upload_list(
        validate_iris_upload,
        minimum=settings.AUTH_IRIS_SAMPLES,
    )
    voice_file = serializers.FileField(validators=[validate_voice_upload])
    eye_side = serializers.ChoiceField(choices=["LEFT", "RIGHT"], default="LEFT")
    challenge_phrase = serializers.CharField(required=False, allow_blank=True)
    # Signed single-use token from a verified liveness challenge (required in
    # production, where FACE_LIVENESS_REQUIRED=True).
    liveness_challenge = serializers.CharField(required=False, allow_blank=True)


class BiometricEnrollmentRequestSerializer(serializers.Serializer):
    face_files = _upload_list(
        validate_face_upload,
        minimum=settings.MIN_FACE_SAMPLES,
    )
    iris_files = _upload_list(
        validate_iris_upload,
        minimum=settings.MIN_IRIS_SAMPLES,
    )
    voice_files = _upload_list(
        validate_voice_upload,
        minimum=settings.MIN_VOICE_SAMPLES,
    )
    eye_side = serializers.ChoiceField(choices=["LEFT", "RIGHT"], default="LEFT")
    # Signed single-use token from a verified liveness challenge (required in
    # production, where FACE_LIVENESS_REQUIRED=True).
    liveness_challenge = serializers.CharField(required=False, allow_blank=True)


class BankingCustomerSerializer(serializers.ModelSerializer):
    biometric_user_id = serializers.UUIDField(source="biometric_user.id", read_only=True)
    enrollment_status = serializers.CharField(
        source="biometric_user.enrollment_status",
        read_only=True,
    )
    enrolled_eye_side = serializers.CharField(
        source="biometric_user.enrolled_eye_side",
        read_only=True,
    )

    class Meta:
        model = BankingCustomer
        fields = (
            "id",
            "customer_id",
            "full_name",
            "mobile_number",
            "biometric_user_id",
            "enrollment_status",
            "enrolled_eye_side",
            "created_at",
            "last_login_at",
        )


class BankingRegisterSerializer(serializers.Serializer):
    duplicate_mobile_message = (
        "This mobile number is already registered. Log in with your existing "
        "customer ID and PIN to continue or complete biometric enrollment."
    )
    full_name = serializers.CharField(max_length=255, trim_whitespace=True)
    mobile_number = serializers.CharField(max_length=20, trim_whitespace=True)
    pin = serializers.CharField(min_length=4, max_length=4, write_only=True)

    def validate_mobile_number(self, value: str) -> str:
        if not value.isascii() or not value.isdigit() or len(value) < 10:
            raise serializers.ValidationError("Enter a valid mobile number.")
        if BankingCustomer.objects.filter(mobile_number=value).exists():
            raise serializers.ValidationError(self.duplicate_mobile_message)
        return value

    def validate_pin(self, value: str) -> str:
        if not value.isascii() or not value.isdigit():
            raise serializers.ValidationError("PIN must contain only digits.")
        return value

    def create(self, validated_data: dict) -> BankingCustomer:
        pin = validated_data.pop("pin")
        pin_hash = make_password(pin)

        # Database uniqueness remains the authority. Each attempt uses its own
        # savepoint so a rare collision can be retried safely under concurrency.
        for _ in range(12):
            customer_id = str(secrets.randbelow(900_000) + 100_000)
            try:
                with transaction.atomic():
                    biometric_user = BiometricUser.objects.create(
                        external_id=customer_id,
                        full_name=validated_data["full_name"],
                    )
                    customer = BankingCustomer.objects.create(
                        biometric_user=biometric_user,
                        customer_id=customer_id,
                        pin_hash=pin_hash,
                        **validated_data,
                    )
                    append_registration(customer)
                    return customer
            except IntegrityError:
                if BankingCustomer.objects.filter(
                    mobile_number=validated_data["mobile_number"]
                ).exists():
                    raise serializers.ValidationError(self.duplicate_mobile_message)
                continue

        raise serializers.ValidationError(
            "Could not allocate a unique customer ID. Please try again."
        )

    def create_session_payload(self, customer: BankingCustomer) -> dict:
        token = signing.dumps(
            {
                "customer_id": str(customer.id),
                "biometric_user_id": str(customer.biometric_user_id),
            },
            salt="banking-login",
        )
        return {
            "token": token,
            "customer": BankingCustomerSerializer(customer).data,
            "next_step": "BIOMETRIC_ENROLLMENT",
        }


class BankingLoginSerializer(serializers.Serializer):
    customer_id = serializers.RegexField(
        r"^[0-9]+$", max_length=64, trim_whitespace=True,
        error_messages={"invalid": "Invalid customer ID. Use digits only."},
    )
    pin = serializers.CharField(min_length=4, max_length=4, write_only=True)

    default_error_messages = {
        "customer_not_found": "Customer ID does not exist. Check the number or create an account.",
        "incorrect_pin": "Incorrect PIN. Please try again.",
    }

    def validate_pin(self, value: str) -> str:
        if not value.isascii() or not value.isdigit():
            raise serializers.ValidationError("PIN must contain only digits.")
        return value

    def validate(self, attrs: dict) -> dict:
        customer_id = attrs["customer_id"]
        try:
            customer = BankingCustomer.objects.select_related(
                "biometric_user",
            ).get(customer_id__iexact=customer_id)
        except BankingCustomer.DoesNotExist as exc:
            raise serializers.ValidationError(
                self.error_messages["customer_not_found"], code="customer_not_found",
            ) from exc

        pin_valid = check_password(attrs["pin"], customer.pin_hash)
        if not pin_valid:
            raise serializers.ValidationError(
                self.error_messages["incorrect_pin"], code="incorrect_pin",
            )

        attrs["customer"] = customer
        return attrs

    def create_session_payload(self) -> dict:
        customer = self.validated_data["customer"]
        token = signing.dumps(
            {
                "customer_id": str(customer.id),
                "biometric_user_id": str(customer.biometric_user_id),
            },
            salt="banking-login",
        )
        return {
            "token": token,
            "customer": BankingCustomerSerializer(customer).data,
            "next_step": (
                "BIOMETRIC_VERIFICATION"
                if customer.biometric_user.is_enrolled
                else "BIOMETRIC_ENROLLMENT"
            ),
        }


class AuthenticationAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthenticationAttempt
        fields = ("id", "saved", "saved_at", "decision", "processing_time_ms")
