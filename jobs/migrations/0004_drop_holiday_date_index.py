from django.db import migrations


def drop_holiday_unique_index(apps, schema_editor):
    db = getattr(schema_editor.connection, "connection", None)
    if db is None:
        return
    collection = db["jobs_holiday"]
    try:
        collection.drop_index("date_1")
    except Exception:
        # Index may not exist; ignore.
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0003_auto_20251120_1502"),
    ]

    operations = [
        migrations.RunPython(drop_holiday_unique_index, migrations.RunPython.noop),
    ]
