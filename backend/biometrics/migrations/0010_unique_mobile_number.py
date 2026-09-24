from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("biometrics", "0009_numeric_customer_ids")]

    operations = [
        migrations.AlterField(
            model_name="bankingcustomer",
            name="mobile_number",
            field=models.CharField(max_length=20, unique=True),
        ),
    ]
