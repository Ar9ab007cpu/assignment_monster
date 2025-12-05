from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0001_management_system'),
    ]

    operations = [
        migrations.CreateModel(
            name='GemCostRule',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(choices=[('summary', 'Summary generation'), ('structure', 'Structure generation'), ('content', 'Content generation (per 200 words)'), ('monster', 'Monster generation')], max_length=32, unique=True)),
                ('cost', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ('key',)},
        ),
    ]
