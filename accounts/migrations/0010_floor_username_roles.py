from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_auto_20251120_1350"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="floor_username",
            field=models.CharField(blank=True, db_index=True, max_length=32, null=True),
        ),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("marketing", "Marketing Team"),
                    ("super_admin", "Super Admin"),
                    ("co_super_admin", "Co Super Admin"),
                    ("global", "Global User"),
                    ("floor", "Floor User"),
                ],
                default="marketing",
                max_length=32,
            ),
        ),
    ]
