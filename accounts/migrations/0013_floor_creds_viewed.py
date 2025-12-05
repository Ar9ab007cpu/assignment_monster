from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_floorsignuprequest"),
    ]

    operations = [
        migrations.AddField(
            model_name="floorsignuprequest",
            name="creds_viewed",
            field=models.BooleanField(default=False),
        ),
    ]
