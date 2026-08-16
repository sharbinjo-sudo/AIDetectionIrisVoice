from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from biometrics.models import BiometricUser, EnrollmentStatus
from biometrics.services.engines import get_iris_engine, get_voice_engine
from biometrics.services.exceptions import BiometricServiceError


class Command(BaseCommand):
    help = "Create or update a biometric user from reference iris and voice samples."

    def add_arguments(self, parser):
        parser.add_argument("--external-id", required=True)
        parser.add_argument("--full-name", required=True)
        parser.add_argument("--iris-file", required=True)
        parser.add_argument("--voice-file", required=True)
        parser.add_argument("--eye-side", default="LEFT", choices=["LEFT", "RIGHT"])

    def handle(self, *args, **options):
        iris_file = Path(options["iris_file"]).expanduser()
        voice_file = Path(options["voice_file"]).expanduser()
        if not iris_file.exists():
            raise CommandError(f"Iris file not found: {iris_file}")
        if not voice_file.exists():
            raise CommandError(f"Voice file not found: {voice_file}")

        try:
            iris_sample = get_iris_engine().extract_features(
                str(iris_file),
                eye_side=options["eye_side"],
            )
            voice_sample = get_voice_engine().extract_features(str(voice_file))
        except BiometricServiceError as exc:
            raise CommandError(str(exc)) from exc

        if not iris_sample.iris_detected:
            raise CommandError(
                "The iris reference image did not produce a detectable eye crop."
            )
        if iris_sample.quality_score < settings.IRIS_QUALITY_THRESHOLD:
            raise CommandError(
                "The iris reference image quality was below the configured threshold."
            )
        if voice_sample.duration_seconds < settings.VOICE_MIN_SECONDS:
            raise CommandError(
                "The voice reference sample is shorter than the configured minimum duration."
            )
        if voice_sample.quality_score < settings.VOICE_QUALITY_THRESHOLD:
            raise CommandError(
                "The voice reference sample quality was below the configured threshold."
            )

        user, _created = BiometricUser.objects.get_or_create(
            external_id=options["external_id"],
            defaults={"full_name": options["full_name"]},
        )
        user.full_name = options["full_name"]
        user.enrollment_status = EnrollmentStatus.COMPLETE
        user.enrolled_eye_side = options["eye_side"]
        user.iris_embedding = iris_sample.embedding
        user.voice_embedding = voice_sample.embedding
        user.iris_quality_score = iris_sample.quality_score
        user.voice_quality_score = voice_sample.quality_score
        user.last_enrolled_at = timezone.now()
        user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"User {user.external_id} enrolled successfully with pretrained embeddings."
            )
        )
