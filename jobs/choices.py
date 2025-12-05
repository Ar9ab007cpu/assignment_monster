"""Shared enums/choices for job workflow."""

from django.db import models


class JobStatus(models.TextChoices):
    NEW = "new", "New"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    ARCHIVED = "archived", "Archived"


class ContentSectionType(models.TextChoices):
    SUMMARY = "summary", "Job Summary"
    STRUCTURE = "structure", "Job Structure"
    CONTENT = "content", "Content"
    REFERENCING = "referencing", "Referencing"
    PLAG_REPORT = "plag_report", "Plag Report"
    AI_REPORT = "ai_report", "AI Report"
    FULL_CONTENT = "full_content", "Full Content"


class ContentStatus(models.TextChoices):
    WAITING = "waiting", "Waiting"
    GENERATED = "generated", "Generated"
    REGENERATE = "regenerate", "Needs Regeneration"
    APPROVED = "approved", "Approved"
