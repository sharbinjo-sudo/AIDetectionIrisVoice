from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from biometrics.services.engines import get_iris_engine, get_voice_engine
from biometrics.services.face_engine import get_face_engine


class Command(BaseCommand):
    help = "Initializes the local face, voice, and iris models."

    def handle(self, *args, **options):
        del args, options

        face_health = get_face_engine().health()
        voice_health = get_voice_engine().health()
        iris_health = get_iris_engine().health()

        self.stdout.write(
            self.style.NOTICE(
                f"Face model: {face_health['name']} | mode={face_health.get('mode', 'unknown')} | ready={face_health['ready']}"
            )
        )
        self.stdout.write(
            self.style.NOTICE(
                f"Voice model: {voice_health['name']} | mode={voice_health.get('mode', 'unknown')} | ready={voice_health['ready']}"
            )
        )
        self.stdout.write(
            self.style.NOTICE(
                f"Iris model: {iris_health['name']} | mode={iris_health.get('mode', 'unknown')} | ready={iris_health['ready']}"
            )
        )

        if not face_health["ready"]:
            self.stdout.write(self.style.ERROR(str(face_health.get("detail"))))
        if not voice_health["ready"]:
            self.stdout.write(self.style.ERROR(str(voice_health.get("detail"))))
        if not iris_health["ready"]:
            self.stdout.write(self.style.ERROR(str(iris_health.get("detail"))))

        if not face_health["ready"] or not voice_health["ready"] or not iris_health["ready"]:
            raise CommandError("One or more local biometric models failed to warm.")

        if (
            face_health.get("mode") == "local_buffalo_l"
            and voice_health.get("mode") in {"pretrained", "local_pretrained"}
            and iris_health.get("mode") in {"pretrained", "local_onnx"}
        ):
            message = "Biometric models are ready for local verification."
        else:
            message = (
                "The backend is ready for local verification. One or more checks are using a quality fallback instead of a deployed model."
            )
        self.stdout.write(self.style.SUCCESS(message))
