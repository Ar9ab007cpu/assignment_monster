from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        ("marketing", "0002_monsterhistory"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReferencingHistory",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content_input", models.TextField()),
                ("reference_style", models.CharField(blank=True, default="", max_length=64)),
                ("reference_count", models.IntegerField(default=0)),
                ("result", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="referencing_histories",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at", "-id"),
            },
        ),
    ]
