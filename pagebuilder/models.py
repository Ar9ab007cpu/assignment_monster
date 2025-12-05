from django.conf import settings
from django.db import models


class AnimationPreset(models.Model):
    """Reusable animation tokens applied to blocks/themes."""

    name = models.CharField(max_length=64, unique=True)
    css_class = models.CharField(
        max_length=128,
        help_text="CSS class to apply for this animation (defined in theme stylesheet).",
    )
    duration_ms = models.PositiveIntegerField(default=600)
    easing = models.CharField(max_length=64, blank=True, default="ease")
    delay_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Theme(models.Model):
    """Theme tokens injected as CSS variables for rendering."""

    name = models.CharField(max_length=64, unique=True)
    primary_color = models.CharField(max_length=32, default="#0d6efd")
    secondary_color = models.CharField(max_length=32, default="#6c757d")
    accent_color = models.CharField(max_length=32, default="#20c997")
    background = models.CharField(
        max_length=128,
        default="linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)",
    )
    font_family = models.CharField(
        max_length=128,
        default="'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif'",
    )
    base_font_size = models.CharField(max_length=16, default="16px")
    spacing_scale = models.JSONField(
        default=list,
        help_text="List of spacing tokens in px (e.g. [4,8,12,16,24,32]).",
    )
    radius = models.CharField(max_length=16, default="12px")
    shadow = models.CharField(max_length=128, default="0 10px 30px rgba(0,0,0,0.08)")
    animation = models.ForeignKey(
        AnimationPreset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="themes",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class PageTemplate(models.Model):
    """Top-level definition for a marketing page."""

    class Slugs(models.TextChoices):
        MARKETING_WELCOME = "marketing_welcome", "Marketing Welcome"
        MARKETING_DASHBOARD = "marketing_dashboard", "Marketing Dashboard"
        MARKETING_ALL_PROJECTS = "marketing_all_projects", "Marketing All Projects"
        MARKETING_HISTORY = "marketing_history", "Marketing History"
        MARKETING_DELETED_JOBS = "marketing_deleted_jobs", "Marketing Deleted Jobs"
        MARKETING_JOB_DETAIL = "marketing_job_detail", "Marketing Job Detail"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    theme = models.ForeignKey(
        Theme, null=True, blank=True, on_delete=models.SET_NULL, related_name="pages"
    )
    allowed_roles = models.JSONField(default=list, blank=True)
    managed_by_roles = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="page_templates_created",
        on_delete=models.SET_NULL,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="page_templates_updated",
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("slug",)

    def __str__(self):
        return self.name

    def is_allowed_for(self, role):
        return not self.allowed_roles or role in self.allowed_roles

    def is_manageable_by(self, role):
        return not self.managed_by_roles or role in self.managed_by_roles


class PageBlock(models.Model):
    """Individual block of content/layout for a page."""

    class BlockType(models.TextChoices):
        HERO = "hero", "Hero"
        CARD_LIST = "card_list", "Cards"
        TABLE = "table", "Table"
        BUTTON_ROW = "button_row", "Button Row"
        TEXT = "text", "Text"
        STATS = "stats", "Stats"
        CUSTOM_HTML = "custom_html", "Custom HTML"

    template = models.ForeignKey(
        PageTemplate, related_name="blocks", on_delete=models.CASCADE
    )
    block_type = models.CharField(
        max_length=32, choices=BlockType.choices, default=BlockType.TEXT
    )
    area = models.CharField(
        max_length=32,
        default="main",
        help_text="Layout area identifier (e.g., main, sidebar, header).",
    )
    order = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=255, blank=True)
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Content/config; supports bindings via `source` and `key` fields.",
    )
    style = models.JSONField(
        default=dict,
        blank=True,
        help_text="Style overrides (colors, spacing, alignment, radius, shadow).",
    )
    animation = models.ForeignKey(
        AnimationPreset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blocks",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("area", "order", "id")

    def __str__(self):
        return f"{self.template.slug} - {self.get_block_type_display()}"
