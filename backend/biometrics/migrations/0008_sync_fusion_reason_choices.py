from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("biometrics", "0007_customer_pin_login")]

    operations = [
        migrations.AlterField(
            model_name="authenticationattempt",
            name="fusion_reason_code",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=64,
                choices=[
                    ("ALL_MODALITIES_VALID", "All Modalities Valid"),
                    ("FACE_VOICE_VALID_IRIS_CAPTURE_ONLY", "Face and Voice Valid; Iris Capture Only"),
                    ("SINGLE_MODALITY_HIGH_CONFIDENCE", "Single Modality High Confidence"),
                    ("IRIS_NOT_DETECTED", "Iris Not Detected"),
                    ("IRIS_QUALITY_TOO_LOW", "Iris Quality Too Low"),
                    ("VOICE_QUALITY_TOO_LOW", "Voice Quality Too Low"),
                    ("VOICE_NO_SPEECH_ACTIVITY", "No Speech Activity"),
                    ("FACE_NOT_DETECTED", "Face Not Detected"),
                    ("FACE_QUALITY_TOO_LOW", "Face Quality Too Low"),
                    ("MULTIPLE_FACES", "Multiple Faces"),
                    ("FUSION_INCONCLUSIVE", "Fusion Inconclusive"),
                    ("NO_VALID_MODALITY", "No Valid Modality"),
                    ("REJECTED_MISMATCH", "Rejected: Mismatch"),
                    ("REJECTED_SPOOF", "Rejected: Spoof"),
                    ("PROCESSING_ERROR", "Processing Error"),
                ],
            ),
        ),
    ]
