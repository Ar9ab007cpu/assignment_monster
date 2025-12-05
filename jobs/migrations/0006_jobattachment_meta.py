from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0005_job_updated_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobattachment",
            name="uploaded_ip",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="jobattachment",
            name="user_agent",
            field=models.CharField(blank=True, max_length=512),
        ),
    ]
