from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_floor_username_roles"),
    ]

    operations = [
        migrations.CreateModel(
            name="InviteCode",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=16, unique=True)),
                ("max_uses", models.PositiveIntegerField(default=1)),
                ("uses", models.PositiveIntegerField(default=0)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
