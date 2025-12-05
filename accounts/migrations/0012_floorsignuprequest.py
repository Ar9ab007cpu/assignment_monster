from django.db import migrations, models
import django.utils.crypto
import django.core.validators
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_invitecode"),
    ]

    operations = [
        migrations.CreateModel(
            name="FloorSignupRequest",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_name", models.CharField(max_length=150)),
                ("last_name", models.CharField(max_length=150)),
                ("email", models.EmailField(max_length=254)),
                ("whatsapp_country_code", models.CharField(default="+91", max_length=5)),
                ("whatsapp_number", models.CharField(max_length=10, validators=[django.core.validators.RegexValidator("^\\d{10}$", "Enter 10 digit number.")])),
                ("last_qualification", models.CharField(max_length=100)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")], default="pending", max_length=20)),
                ("generated_username", models.CharField(blank=True, max_length=32)),
                ("generated_password", models.CharField(blank=True, max_length=64)),
                ("request_token", models.CharField(default=django.utils.crypto.get_random_string, max_length=64, unique=True)),
                ("decision_notes", models.TextField(blank=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("decided_by", models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="floor_requests_processed", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
