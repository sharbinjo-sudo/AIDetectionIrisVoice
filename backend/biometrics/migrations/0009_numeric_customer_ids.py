from django.db import migrations


def numeric_customer_ids(apps, schema_editor):
    Customer = apps.get_model("biometrics", "BankingCustomer")
    customers = Customer.objects.using(schema_editor.connection.alias)
    used = set(customers.values_list("customer_id", flat=True))
    candidate = 100000
    for customer in customers.order_by("id").iterator():
        if customer.customer_id.isascii() and customer.customer_id.isdigit():
            continue
        while str(candidate) in used:
            candidate += 1
        new_id = str(candidate)
        customers.filter(pk=customer.pk).update(customer_id=new_id)
        used.add(new_id)
        candidate += 1


class Migration(migrations.Migration):
    dependencies = [("biometrics", "0008_sync_fusion_reason_choices")]
    # Identity UUIDs, PIN hashes and all template records remain unchanged.
    operations = [migrations.RunPython(numeric_customer_ids)]
