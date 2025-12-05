from django.conf import settings
from django.db import models


class FormDefinition(models.Model):
    """Top-level form metadata."""

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    allowed_roles = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("slug",)

    def __str__(self):
        return self.name


class FormField(models.Model):
    """Configurable fields for a form definition."""

    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        TEXTAREA = "textarea", "Textarea"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        DATETIME = "datetime", "DateTime"
        SELECT = "select", "Select"
        FILE = "file", "File"

    definition = models.ForeignKey(
        FormDefinition, related_name="fields", on_delete=models.CASCADE
    )
    name = models.SlugField()
    label = models.CharField(max_length=128)
    help_text = models.CharField(max_length=255, blank=True)
    field_type = models.CharField(
        max_length=32, choices=FieldType.choices, default=FieldType.TEXT
    )
    order = models.PositiveIntegerField(default=0)
    required_roles = models.JSONField(default=list, blank=True)
    visible_roles = models.JSONField(default=list, blank=True)
    read_only_roles = models.JSONField(default=list, blank=True)
    choices = models.JSONField(default=list, blank=True)
    target_field = models.CharField(
        max_length=128,
        help_text="Model field this config controls (e.g., job_id_customer).",
    )
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(
        default=False,
        help_text="System fields are shown for reference and cannot be removed.",
    )

    class Meta:
        ordering = ("order", "id")
        unique_together = ("definition", "name")

    def __str__(self):
        return f"{self.definition.slug}.{self.name}"

    def is_visible_for(self, role):
        roles = self.visible_roles or []
        return not roles or role in roles

    def is_required_for(self, role):
        roles = self.required_roles or []
        return role in roles
