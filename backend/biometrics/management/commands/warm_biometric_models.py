from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from biometrics.services.engines import get_iris_engine, get_voice_engine


class Command(BaseCommand):
    help = "Downloads and initializes the pretrained voice and iris models."

    def handle(self, *args, **options):
        del args, options

        voice_health = get_voice_engine().health()
        iris_health = get_iris_engine().health()

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

        if not voice_health["ready"]:
            self.stdout.write(self.style.ERROR(str(voice_health.get("detail"))))
        if not iris_health["ready"]:
            self.stdout.write(self.style.ERROR(str(iris_health.get("detail"))))

        if not voice_health["ready"] or not iris_health["ready"]:
            raise CommandError("One or more pretrained biometric models failed to warm.")

        if (
            voice_health.get("mode") in {"pretrained", "local_pretrained"}
            and iris_health.get("mode") in {"pretrained", "local_onnx"}
        ):
            message = "Biometric models are ready for local verification."
        else:
            message = (
                "The backend is ready for local verification. One or more checks are using the built-in fallback mode instead of the pretrained model."
            )
        self.stdout.write(self.style.SUCCESS(message))



