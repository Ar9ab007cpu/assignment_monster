from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AnimationPreset",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64, unique=True)),
                ("css_class", models.CharField(help_text="CSS class to apply for this animation (defined in theme stylesheet).", max_length=128)),
                ("duration_ms", models.PositiveIntegerField(default=600)),
                ("easing", models.CharField(blank=True, default="ease", max_length=64)),
                ("delay_ms", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="Theme",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64, unique=True)),
                ("primary_color", models.CharField(default="#0d6efd", max_length=32)),
                ("secondary_color", models.CharField(default="#6c757d", max_length=32)),
                ("accent_color", models.CharField(default="#20c997", max_length=32)),
                ("background", models.CharField(default="linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)", max_length=128)),
                ("font_family", models.CharField(default="'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif'", max_length=128)),
                ("base_font_size", models.CharField(default="16px", max_length=16)),
                ("spacing_scale", models.JSONField(default=list, help_text="List of spacing tokens in px (e.g. [4,8,12,16,24,32]).")),
                ("radius", models.CharField(default="12px", max_length=16)),
                ("shadow", models.CharField(default="0 10px 30px rgba(0,0,0,0.08)", max_length=128)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("animation", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="themes", to="pagebuilder.animationpreset")),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="PageTemplate",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(unique=True)),
                ("name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True)),
                ("allowed_roles", models.JSONField(blank=True, default=list)),
                ("managed_by_roles", models.JSONField(blank=True, default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="page_templates_created", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="page_templates_updated", to=settings.AUTH_USER_MODEL)),
                ("theme", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="pages", to="pagebuilder.theme")),
            ],
            options={"ordering": ("slug",)},
        ),
        migrations.CreateModel(
            name="PageBlock",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("block_type", models.CharField(choices=[("hero", "Hero"), ("card_list", "Cards"), ("table", "Table"), ("button_row", "Button Row"), ("text", "Text"), ("stats", "Stats"), ("custom_html", "Custom HTML")], default="text", max_length=32)),
                ("area", models.CharField(default="main", help_text="Layout area identifier (e.g., main, sidebar, header).", max_length=32)),
                ("order", models.PositiveIntegerField(default=1)),
                ("title", models.CharField(blank=True, max_length=255)),
                ("data", models.JSONField(blank=True, default=dict, help_text="Content/config; supports bindings via `source` and `key` fields.")),
                ("style", models.JSONField(blank=True, default=dict, help_text="Style overrides (colors, spacing, alignment, radius, shadow).")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("animation", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="blocks", to="pagebuilder.animationpreset")),
                ("template", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="blocks", to="pagebuilder.pagetemplate")),
            ],
            options={"ordering": ("area", "order", "id")},
        ),
    ]
