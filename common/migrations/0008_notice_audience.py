from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0007_activitylogarchive_errorlogarchive"),
    ]

    operations = [
        migrations.AddField(
            model_name="notice",
            name="show_on_global",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="notice",
            name="show_on_marketing",
            field=models.BooleanField(default=True),
        ),
    ]
