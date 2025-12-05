from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0005_notice_activitylog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ErrorLog",
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
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="resolved_error_logs", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="error_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
    ]
