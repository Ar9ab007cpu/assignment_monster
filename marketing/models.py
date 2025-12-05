from django.db import models
from django.conf import settings


class AnalyzeHistory(models.Model):
    """Persisted history for global analyze (summary) generations."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="analyze_histories"
    )
    instruction = models.TextField()
    result = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")


class StructureHistory(models.Model):
    """Persisted history for global structure generations."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="structure_histories"
    )
    summary = models.TextField()
    result = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")


class ContentHistory(models.Model):
    """Persisted history for global content generations."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="content_histories"
    )
    structure = models.TextField()
    result = models.TextField()
    word_count = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")


class MonsterHistory(models.Model):
    """History of Monster Click generations."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="monster_histories"
    )
    instruction = models.TextField(blank=True, default="")
    result = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")


class ReferencingHistory(models.Model):
    """History for global referencing generations."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referencing_histories"
    )
    content_input = models.TextField()
    reference_style = models.CharField(max_length=64, blank=True, default="")
    reference_count = models.IntegerField(default=0)
    result = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
