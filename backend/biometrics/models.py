from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class EnrollmentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    COMPLETE = "COMPLETE", "Complete"
    FAILED = "FAILED", "Failed"


class EyeSide(models.TextChoices):
    LEFT = "LEFT", "Left"
    RIGHT = "RIGHT", "Right"


class Decision(models.TextChoices):
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"
    REJECTED_MISMATCH = "REJECTED_MISMATCH", "Rejected: Mismatch"
    REJECTED_SPOOF = "REJECTED_SPOOF", "Rejected: Spoof"
    RETRY_REQUIRED = "RETRY_REQUIRED", "Retry Required"
    PROCESSING_ERROR = "PROCESSING_ERROR", "Processing Error"


class DecisionReason(models.TextChoices):
    """Machine-readable reason codes; see services/fusion.py ReasonCode."""

    ALL_MODALITIES_VALID = "ALL_MODALITIES_VALID", "All Modalities Valid"
    FACE_VOICE_VALID_IRIS_CAPTURE_ONLY = (
        "FACE_VOICE_VALID_IRIS_CAPTURE_ONLY",
        "Face and Voice Valid; Iris Capture Only",
    )
    SINGLE_MODALITY_HIGH_CONFIDENCE = (
        "SINGLE_MODALITY_HIGH_CONFIDENCE",
        "Single Modality High Confidence",
    )
    IRIS_NOT_DETECTED = "IRIS_NOT_DETECTED", "Iris Not Detected"
    IRIS_QUALITY_TOO_LOW = "IRIS_QUALITY_TOO_LOW", "Iris Quality Too Low"
    VOICE_QUALITY_TOO_LOW = "VOICE_QUALITY_TOO_LOW", "Voice Quality Too Low"
    VOICE_NO_SPEECH_ACTIVITY = (
        "VOICE_NO_SPEECH_ACTIVITY",
        "No Speech Activity",
    )
    FACE_NOT_DETECTED = "FACE_NOT_DETECTED", "Face Not Detected"
    FACE_QUALITY_TOO_LOW = "FACE_QUALITY_TOO_LOW", "Face Quality Too Low"
    MULTIPLE_FACES = "MULTIPLE_FACES", "Multiple Faces"
    FUSION_INCONCLUSIVE = "FUSION_INCONCLUSIVE", "Fusion Inconclusive"
    NO_VALID_MODALITY = "NO_VALID_MODALITY", "No Valid Modality"
    REJECTED_MISMATCH = "REJECTED_MISMATCH", "Rejected: Mismatch"
    REJECTED_SPOOF = "REJECTED_SPOOF", "Rejected: Spoof"
    PROCESSING_ERROR = "PROCESSING_ERROR", "Processing Error"


class BiometricUser(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(max_length=64, unique=True)
    full_name = models.CharField(max_length=255)
    enrollment_status = models.CharField(
        max_length=16,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.PENDING,
    )
    enrolled_eye_side = models.CharField(
        max_length=8,
        choices=EyeSide.choices,
        default=EyeSide.LEFT,
    )
    iris_embedding = models.JSONField(default=list, blank=True)
    voice_embedding = models.JSONField(default=list, blank=True)
    # Versioned, encrypted templates. The legacy JSON fields above remain for
    # migration compatibility and are cleared whenever enrollment is renewed.
    face_template_encrypted = models.TextField(blank=True, editable=False)
    iris_template_encrypted = models.TextField(blank=True, editable=False)
    voice_template_encrypted = models.TextField(blank=True, editable=False)
    template_version = models.PositiveSmallIntegerField(default=2)
    face_quality_score = models.FloatField(null=True, blank=True)
    iris_quality_score = models.FloatField(null=True, blank=True)
    voice_quality_score = models.FloatField(null=True, blank=True)
    face_sample_count = models.PositiveSmallIntegerField(default=0)
    iris_sample_count = models.PositiveSmallIntegerField(default=0)
    voice_sample_count = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)
    last_enrolled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name", "external_id"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.external_id})"

    @property
    def is_enrolled(self) -> bool:
        base_enrolled = (
            self.enrollment_status == EnrollmentStatus.COMPLETE
            and bool(self.face_template_encrypted)
            and bool(self.voice_template_encrypted or self.voice_embedding)
        )
        if getattr(settings, "FACE_PRIMARY_CAPTURE_MODE", False):
            return base_enrolled
        return base_enrolled and bool(self.iris_template_encrypted or self.iris_embedding)


class BankingCustomer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    biometric_user = models.OneToOneField(
        BiometricUser,
        on_delete=models.CASCADE,
        related_name="banking_customer",
    )
    customer_id = models.CharField(max_length=64, unique=True)
    full_name = models.CharField(max_length=255)
    mobile_number = models.CharField(max_length=20, unique=True)
    pin_hash = models.CharField(max_length=255)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name", "customer_id"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.customer_id})"


class AuthenticationAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Nullable: anonymous IRL verification attempts (no enrolled identity)
    # are recorded for quality monitoring without any user linkage.
    user = models.ForeignKey(
        BiometricUser,
        on_delete=models.CASCADE,
        related_name="authentication_attempts",
        null=True,
        blank=True,
    )

    face_raw_score = models.FloatField(null=True, blank=True)
    face_normalized_score = models.FloatField(null=True, blank=True)
    face_threshold = models.FloatField(null=True, blank=True)
    face_quality_score = models.FloatField(null=True, blank=True)
    face_detection_confidence = models.FloatField(null=True, blank=True)
    face_valid_measurement = models.BooleanField(default=False)
    face_passed = models.BooleanField(default=False)

    iris_raw_score = models.FloatField(null=True, blank=True)
    iris_normalized_score = models.FloatField(null=True, blank=True)
    iris_threshold = models.FloatField(null=True, blank=True)
    iris_quality_score = models.FloatField(null=True, blank=True)
    iris_passed = models.BooleanField(default=False)

    voice_raw_score = models.FloatField(null=True, blank=True)
    voice_normalized_score = models.FloatField(null=True, blank=True)
    voice_threshold = models.FloatField(null=True, blank=True)
    voice_quality_score = models.FloatField(null=True, blank=True)
    voice_passed = models.BooleanField(default=False)

    iris_detection_confidence = models.FloatField(null=True, blank=True)
    iris_valid_measurement = models.BooleanField(default=False)
    voice_valid_measurement = models.BooleanField(default=False)

    fusion_voice_weight = models.FloatField(default=0.5)
    fusion_iris_weight = models.FloatField(default=0.5)
    fusion_face_weight = models.FloatField(default=0.0)
    fusion_score = models.FloatField(default=0.0)
    fusion_threshold = models.FloatField(default=0.8)
    fusion_reason_code = models.CharField(
        max_length=64,
        choices=DecisionReason.choices,
        null=True,
        blank=True,
    )

    decision = models.CharField(
        max_length=32,
        choices=Decision.choices,
        default=Decision.PROCESSING_ERROR,
    )
    failure_reason = models.TextField(null=True, blank=True)
    processing_time_ms = models.PositiveIntegerField(default=0)
    saved = models.BooleanField(default=False)
    saved_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        identity = self.user.external_id if self.user else "anonymous"
        return f"{identity} - {self.decision} - {self.created_at:%Y-%m-%d %H:%M:%S}"
