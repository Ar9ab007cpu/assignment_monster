from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0001_initial"),
        ("tickets", "0003_ticket_reported_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="category",
            field=models.CharField(
                choices=[("general", "General"), ("deadline_change", "Deadline Change")],
                default="general",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="ticket",
            name="job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="tickets",
                to="jobs.job",
            ),
        ),
        migrations.AddField(
            model_name="ticket",
            name="requested_expected_deadline",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="requested_strict_deadline",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
