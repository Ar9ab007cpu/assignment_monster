from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("formbuilder", "0003_seed_more_forms"),
    ]

    operations = [
        migrations.AddField(
            model_name="formfield",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
