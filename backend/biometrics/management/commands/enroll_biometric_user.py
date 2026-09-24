from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from biometrics.models import BiometricUser
from biometrics.services.exceptions import BiometricServiceError
from biometrics.services.workflow import enroll_user_biometrics


class Command(BaseCommand):
    help = "Create or update a user from face/iris and multiple voice samples."

    def add_arguments(self, parser):
        parser.add_argument("--external-id", required=True)
        parser.add_argument("--full-name", required=True)
        parser.add_argument(
            "--face-file",
            required=True,
            action="append",
            help="Face image (repeat at least MIN_FACE_SAMPLES times).",
        )
        parser.add_argument(
            "--iris-file",
            required=True,
            action="append",
            help="Iris image (repeat at least MIN_IRIS_SAMPLES times).",
        )
        parser.add_argument(
            "--voice-file",
            required=True,
            action="append",
            help="Voice recording (repeat at least MIN_VOICE_SAMPLES times).",
        )
        parser.add_argument("--eye-side", default="LEFT", choices=["LEFT", "RIGHT"])

    def handle(self, *args, **options):
        face_files = [Path(value).expanduser() for value in options["face_file"]]
        iris_files = [Path(value).expanduser() for value in options["iris_file"]]
        voice_files = [Path(value).expanduser() for value in options["voice_file"]]
        for kind, paths in (("Face", face_files), ("Iris", iris_files)):
            missing = next((path for path in paths if not path.is_file()), None)
            if missing is not None:
                raise CommandError(f"{kind} file not found: {missing}")
        missing_voice = next((path for path in voice_files if not path.is_file()), None)
        if missing_voice is not None:
            raise CommandError(f"Voice file not found: {missing_voice}")

        user, _created = BiometricUser.objects.get_or_create(
            external_id=options["external_id"],
            defaults={"full_name": options["full_name"]},
        )
        user.full_name = options["full_name"]
        user.save(update_fields=["full_name", "updated_at"])
        try:
            result = enroll_user_biometrics(
                user=user,
                face_paths=[str(path) for path in face_files],
                iris_paths=[str(path) for path in iris_files],
                voice_paths=[str(path) for path in voice_files],
                eye_side=options["eye_side"],
            )
        except BiometricServiceError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"User {user.external_id} enrolled: "
                f"{result['face_samples']} face, {result['iris_samples']} iris, "
                f"and {result['voice_samples']} voice samples "
                f"({result['voice_segments']} segments)."
            )
        )
