from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0006_errorlog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ActivityLogArchive",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("path", models.CharField(max_length=512)),
                ("method", models.CharField(max_length=10)),
                ("status_code", models.PositiveIntegerField()),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=512)),
                ("referrer", models.CharField(blank=True, max_length=512)),
                ("duration_ms", models.FloatField(default=0)),
                ("action_type", models.CharField(blank=True, max_length=64)),
                ("extra_meta", models.JSONField(blank=True, default=dict)),
                ("session_key", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField()),
                ("archived_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="activity_logs_archived", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-archived_at",),
            },
        ),
        migrations.CreateModel(
            name="ErrorLogArchive",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("path", models.CharField(max_length=512)),
                ("method", models.CharField(max_length=10)),
                ("status_code", models.PositiveIntegerField(default=500)),
                ("message", models.TextField(blank=True)),
                ("traceback", models.TextField(blank=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=512)),
                ("referrer", models.CharField(blank=True, max_length=512)),
                ("resolved", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField()),
                ("archived_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="error_logs_archived", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-archived_at",),
            },
        ),
    ]
