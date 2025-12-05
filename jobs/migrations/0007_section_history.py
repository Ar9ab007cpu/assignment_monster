from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0006_jobattachment_meta'),
    ]

    operations = [
        migrations.CreateModel(
            name='JobContentSectionHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(blank=True, default='regenerate', max_length=32)),
                ('content', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('section', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='histories', to='jobs.jobcontentsection')),
            ],
            options={
                'ordering': ('-created_at',),
            },
        ),
    ]
