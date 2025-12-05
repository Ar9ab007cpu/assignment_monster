from django.db import migrations, models


def seed_management_systems(apps, schema_editor):
    ManagementSystem = apps.get_model("common", "ManagementSystem")
    defaults = [
        {
            "key": "signup_login",
            "name": "Signup & Login Management",
            "description": "Control whether users can sign up or log in to the portal.",
        },
        {
            "key": "profile_management",
            "name": "Profile Management",
            "description": "Enable profile pages and profile update workflows.",
        },
        {
            "key": "user_management",
            "name": "User Management",
            "description": "Allow moderation of pending users and approvals.",
        },
        {
            "key": "website_content",
            "name": "Website Content Management",
            "description": "Toggle project/job dashboards and related features.",
        },
    ]
    for data in defaults:
        ManagementSystem.objects.get_or_create(
            key=data["key"],
            defaults=data,
        )


def remove_management_systems(apps, schema_editor):
    ManagementSystem = apps.get_model("common", "ManagementSystem")
    ManagementSystem.objects.filter(
        key__in=[
            "signup_login",
            "profile_management",
            "user_management",
            "website_content",
        ]
    ).delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ManagementSystem",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(choices=[("signup_login", "Signup & Login Management"), ("profile_management", "Profile Management"), ("user_management", "User Management"), ("website_content", "Website Content Management")], max_length=64, unique=True)),
                ("name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True)),
                ("enabled_for_accounts", models.BooleanField(default=True)),
                ("enabled_for_marketing", models.BooleanField(default=True)),
                ("enabled_for_superadmins", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("name",),
            },
        ),
        migrations.RunPython(seed_management_systems, remove_management_systems),
    ]
