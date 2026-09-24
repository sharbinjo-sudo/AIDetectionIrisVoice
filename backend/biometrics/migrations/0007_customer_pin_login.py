from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("biometrics", "0006_authenticationattempt_face_detection_confidence_and_more"),
    ]

    operations = [
        migrations.RemoveField(model_name="bankingcustomer", name="account_number"),
        migrations.RemoveField(model_name="bankingcustomer", name="password_hash"),
    ]
