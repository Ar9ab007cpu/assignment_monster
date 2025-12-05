from django.db import migrations


def add_system_control(apps, schema_editor):
    NavigationItem = apps.get_model("navbuilder", "NavigationItem")
    for role in ["super_admin", "co_super_admin"]:
        NavigationItem.objects.get_or_create(
            role=role,
            label="System Control",
            url_name="superadmin:system_control",
            defaults={
                "order": 99,
                "is_active": True,
                "badge_key": "",
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("navbuilder", "0002_seed_nav"),
    ]

    operations = [
        migrations.RunPython(add_system_control, migrations.RunPython.noop),
    ]
