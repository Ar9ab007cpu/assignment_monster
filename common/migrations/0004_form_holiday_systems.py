from django.db import migrations, models


def add_form_holiday_systems(apps, schema_editor):
    ManagementSystem = apps.get_model("common", "ManagementSystem")
    defaults = [
        {
            "key": "form_management",
            "name": "Form Management",
            "description": "Toggle marketing job drop and other form submissions.",
        },
        {
            "key": "holiday_management",
            "name": "Holiday Management",
            "description": "Control holiday calendar to block deadlines.",
        },
    ]
    for data in defaults:
        ManagementSystem.objects.get_or_create(
            key=data["key"],
            defaults=data,
        )


def remove_form_holiday_systems(apps, schema_editor):
    ManagementSystem = apps.get_model("common", "ManagementSystem")
    ManagementSystem.objects.filter(
        key__in=["form_management", "holiday_management"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0003_auto_20251119_1816"),
    ]

    operations = [
        migrations.AlterField(
            model_name="managementsystem",
            name="key",
            field=models.CharField(
                choices=[
                    ("signup_login", "Signup & Login Management"),
                    ("profile_management", "Profile Management"),
                    ("user_management", "User Management"),
                    ("website_content", "Website Content Management"),
                    ("ticket_management", "Ticket Management"),
                    ("form_management", "Form Management"),
                    ("holiday_management", "Holiday Management"),
                ],
                max_length=64,
                unique=True,
            ),
        ),
        migrations.RunPython(add_form_holiday_systems, remove_form_holiday_systems),
    ]
