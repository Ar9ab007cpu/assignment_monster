from django.db import migrations, models


def populate_reported_fields(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    User = apps.get_model("accounts", "User")
    for ticket in Ticket.objects.all():
        user = None
        if ticket.created_by_id:
            try:
                user = User.objects.get(pk=ticket.created_by_id)
            except User.DoesNotExist:
                user = None
        if user:
            name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email or ""
            ticket.reported_by_name = name or ticket.reported_by_name
            ticket.reported_by_email = user.email or ticket.reported_by_email
            ticket.save(update_fields=["reported_by_name", "reported_by_email"])


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0002_ticket_ticket_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="reported_by_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="ticket",
            name="reported_by_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.RunPython(populate_reported_fields, migrations.RunPython.noop),
    ]
