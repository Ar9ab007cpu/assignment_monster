from django.db import migrations, models
from django.conf import settings

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='AnalyzeHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('instruction', models.TextField()),
                ('result', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='analyze_histories', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-created_at', '-id'),},
        ),
        migrations.CreateModel(
            name='StructureHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('summary', models.TextField()),
                ('result', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='structure_histories', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-created_at', '-id'),},
        ),
        migrations.CreateModel(
            name='ContentHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('structure', models.TextField()),
                ('result', models.TextField()),
                ('word_count', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='content_histories', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-created_at', '-id'),},
        ),
    ]
