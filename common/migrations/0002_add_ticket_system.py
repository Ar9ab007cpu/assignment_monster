from django.db import migrations


def add_ticket_system(apps, schema_editor):
    ManagementSystem = apps.get_model("common", "ManagementSystem")
    ManagementSystem.objects.get_or_create(
        key="ticket_management",
        defaults={
            "name": "Ticket Management",
            "description": "Toggle ticket creation and admin resolution panels.",
            "enabled_for_accounts": True,
            "enabled_for_marketing": True,
            "enabled_for_superadmins": True,
        },
    )


def remove_ticket_system(apps, schema_editor):
    ManagementSystem = apps.get_model("common", "ManagementSystem")
    ManagementSystem.objects.filter(key="ticket_management").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0001_management_system"),
    ]

    operations = [
        migrations.RunPython(add_ticket_system, remove_ticket_system),
    ]
