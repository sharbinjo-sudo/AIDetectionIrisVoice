from __future__ import annotations

import uuid

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
    iris_quality_score = models.FloatField(null=True, blank=True)
    voice_quality_score = models.FloatField(null=True, blank=True)
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
        return (
            self.enrollment_status == EnrollmentStatus.COMPLETE
            and bool(self.iris_embedding)
            and bool(self.voice_embedding)
        )


class AuthenticationAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        BiometricUser,
        on_delete=models.CASCADE,
        related_name="authentication_attempts",
    )

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

    fusion_voice_weight = models.FloatField(default=0.5)
    fusion_iris_weight = models.FloatField(default=0.5)
    fusion_score = models.FloatField(default=0.0)
    fusion_threshold = models.FloatField(default=0.8)

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
        return f"{self.user.external_id} - {self.decision} - {self.created_at:%Y-%m-%d %H:%M:%S}"
