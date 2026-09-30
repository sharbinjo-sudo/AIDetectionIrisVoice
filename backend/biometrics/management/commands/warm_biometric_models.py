from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from biometrics.services.engines import get_iris_engine, get_voice_engine
from biometrics.services.face_engine import get_face_engine
from biometrics.services.face_liveness import get_face_liveness_engine


class Command(BaseCommand):
    help = "Initializes the local face, face liveness, voice, and iris models."

    def handle(self, *args, **options):
        del args, options

        face_health = get_face_engine().health()
        liveness_health = get_face_liveness_engine().health()
        voice_health = get_voice_engine().health()
        iris_health = get_iris_engine().health()

        self.stdout.write(
            self.style.NOTICE(
                f"Face model: {face_health['name']} | mode={face_health.get('mode', 'unknown')} | ready={face_health['ready']}"
            )
        )
        self.stdout.write(
            self.style.NOTICE(
                f"Face liveness model: {liveness_health['name']} | "
                f"mode={liveness_health.get('mode', 'unknown')} | "
                f"ready={liveness_health['ready']}"
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
        if not liveness_health["ready"]:
            self.stdout.write(self.style.ERROR(str(liveness_health.get("detail"))))
        if not voice_health["ready"]:
            self.stdout.write(self.style.ERROR(str(voice_health.get("detail"))))
        if not iris_health["ready"]:
            self.stdout.write(self.style.ERROR(str(iris_health.get("detail"))))

        models_failed = (
            not face_health["ready"]
            or not voice_health["ready"]
            or not iris_health["ready"]
            or (settings.FACE_LIVENESS_REQUIRED and not liveness_health["ready"])
        )
        if models_failed:
            raise CommandError("One or more local biometric models failed to warm.")
        if not liveness_health["ready"]:
            self.stdout.write(
                self.style.WARNING(
                    "The face anti-spoofing model is not ready. Set "
                    "FACE_LIVENESS_REQUIRED=False only for non-production "
                    "diagnostics; face registration and login fail closed "
                    "without it."
                )
            )

        if (
            face_health.get("mode") == "local_buffalo_l"
            and liveness_health.get("mode") == "local_onnx"
            and voice_health.get("mode") in {"pretrained", "local_pretrained"}
            and iris_health.get("mode") in {"pretrained", "local_onnx"}
        ):
            message = "Biometric models are ready for local verification."
        else:
            message = (
                "The backend is ready for local verification. One or more checks are using a quality fallback instead of a deployed model."
            )
        self.stdout.write(self.style.SUCCESS(message))
