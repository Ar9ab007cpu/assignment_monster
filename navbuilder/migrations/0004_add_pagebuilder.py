from django.db import migrations


def add_pagebuilder(apps, schema_editor):
    NavigationItem = apps.get_model("navbuilder", "NavigationItem")
    for role in ["super_admin", "co_super_admin"]:
        NavigationItem.objects.get_or_create(
            role=role,
            label="Page Builder",
            url_name="pagebuilder:templates",
            defaults={
                "order": 98,
                "badge_key": "",
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("navbuilder", "0003_add_system_control"),
    ]

    operations = [
        migrations.RunPython(add_pagebuilder, migrations.RunPython.noop),
    ]
