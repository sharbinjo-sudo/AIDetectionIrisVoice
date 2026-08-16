import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BiometricUser",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("external_id", models.CharField(max_length=64, unique=True)),
                ("full_name", models.CharField(max_length=255)),
                (
                    "enrollment_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("COMPLETE", "Complete"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING",
                        max_length=16,
                    ),
                ),
                (
                    "enrolled_eye_side",
                    models.CharField(
                        choices=[("LEFT", "Left"), ("RIGHT", "Right")],
                        default="LEFT",
                        max_length=8,
                    ),
                ),
                ("iris_embedding", models.JSONField(blank=True, default=list)),
                ("voice_embedding", models.JSONField(blank=True, default=list)),
                ("iris_quality_score", models.FloatField(blank=True, null=True)),
                ("voice_quality_score", models.FloatField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("last_enrolled_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["full_name", "external_id"]},
        ),
        migrations.CreateModel(
            name="AuthenticationAttempt",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("iris_raw_score", models.FloatField(blank=True, null=True)),
                ("iris_normalized_score", models.FloatField(blank=True, null=True)),
                ("iris_threshold", models.FloatField(blank=True, null=True)),
                ("iris_quality_score", models.FloatField(blank=True, null=True)),
                ("iris_passed", models.BooleanField(default=False)),
                ("voice_raw_score", models.FloatField(blank=True, null=True)),
                ("voice_normalized_score", models.FloatField(blank=True, null=True)),
                ("voice_threshold", models.FloatField(blank=True, null=True)),
                ("voice_quality_score", models.FloatField(blank=True, null=True)),
                ("voice_passed", models.BooleanField(default=False)),
                ("fusion_voice_weight", models.FloatField(default=0.5)),
                ("fusion_iris_weight", models.FloatField(default=0.5)),
                ("fusion_score", models.FloatField(default=0.0)),
                ("fusion_threshold", models.FloatField(default=0.8)),
                (
                    "decision",
                    models.CharField(
                        choices=[
                            ("ACCEPTED", "Accepted"),
                            ("REJECTED", "Rejected"),
                            ("PROCESSING_ERROR", "Processing Error"),
                        ],
                        default="PROCESSING_ERROR",
                        max_length=32,
                    ),
                ),
                ("failure_reason", models.TextField(blank=True, null=True)),
                ("processing_time_ms", models.PositiveIntegerField(default=0)),
                ("saved", models.BooleanField(default=False)),
                ("saved_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="authentication_attempts",
                        to="biometrics.biometricuser",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
