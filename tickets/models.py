"""Ticket models for cross-role support."""

import uuid

from django.conf import settings
from django.db import models

from jobs.models import Job


class TicketStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In Progress"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class TicketCategory(models.TextChoices):
    GENERAL = "general", "General"
    TECHNICAL = "technical", "Technical"
    OTHER = "other", "Other"
    DEADLINE_CHANGE = "deadline_change", "Deadline Change"


def generate_ticket_id():
    return f"TCK-{uuid.uuid4().hex[:10].upper()}"


class Ticket(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tickets_created",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets_assigned",
    )
    subject = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(
        max_length=32, choices=TicketCategory.choices, default=TicketCategory.GENERAL
    )
    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets",
    )
    requested_expected_deadline = models.DateTimeField(null=True, blank=True)
    requested_strict_deadline = models.DateTimeField(null=True, blank=True)
    reported_by_name = models.CharField(max_length=255, blank=True)
    reported_by_email = models.EmailField(blank=True)
    ticket_id = models.CharField(
        max_length=24,
        editable=False,
        default=generate_ticket_id,
        db_index=True,
    )
    status = models.CharField(
        max_length=32, choices=TicketStatus.choices, default=TicketStatus.OPEN
    )
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.ticket_id or self.pk} - {self.subject}"

    def can_be_managed_by(self, user):
        from accounts.models import User

        if not user or not user.is_authenticated:
            return False
        return user.role in {User.Role.SUPER_ADMIN, User.Role.CO_SUPER_ADMIN}

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            candidate = generate_ticket_id()
            while Ticket.objects.filter(ticket_id=candidate).exclude(pk=self.pk).exists():
                candidate = generate_ticket_id()
            self.ticket_id = candidate
        if self.created_by and not self.reported_by_name:
            name = (self.created_by.get_full_name() or "").strip()
            self.reported_by_name = name or (self.created_by.email or "")
        if self.created_by and not self.reported_by_email:
            self.reported_by_email = self.created_by.email or ""
        super().save(*args, **kwargs)

    @property
    def raised_by_name(self):
        if self.reported_by_name:
            return self.reported_by_name
        user = self.created_by
        if not user:
            return "Deleted User"
        full = (user.get_full_name() or "").strip()
        if not full:
            full = user.email or self.reported_by_email or "Unknown User"
        return full

    def assigned_to_name(self):
        if not self.assigned_to:
            return "-"
        full = (self.assigned_to.get_full_name() or "").strip()
        return full if full else (self.assigned_to.email or "-")
