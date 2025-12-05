from django.db import migrations, models
from django.conf import settings

class Migration(migrations.Migration):
    dependencies = [
        ('marketing', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MonsterHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('instruction', models.TextField(blank=True, default='')),
                ('result', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='monster_histories', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-created_at', '-id')},
        ),
    ]
