"""Models representing jobs, holidays, sections, and attachments."""

from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .choices import ContentSectionType, ContentStatus, JobStatus


class Holiday(models.Model):
    """Dates on which deadlines cannot be scheduled."""

    date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("date",)

    def __str__(self):
        return f"Holiday {self.date}"

    def clean(self):
        if Holiday.objects.exclude(pk=self.pk).filter(date=self.date).exists():
            raise ValidationError("A holiday already exists for this date.")

        Job = apps.get_model("jobs", "Job")
        conflicts = []
        for job in Job.objects.all():
            if job.is_deleted:
                continue
            if job.expected_deadline and job.expected_deadline.date() == self.date:
                conflicts.append(job)
                continue
            if job.strict_deadline and job.strict_deadline.date() == self.date:
                conflicts.append(job)
        if conflicts:
            raise ValidationError(
                "Cannot mark this date as holiday due to existing job deadlines."
            )


class JobQuerySet(models.QuerySet):
    def _filter_or_exclude(self, negate, *args, **kwargs):
        if "is_deleted" in kwargs:
            val = kwargs.pop("is_deleted")
            kwargs["is_deleted__in"] = [val]
        return super()._filter_or_exclude(negate, *args, **kwargs)

    def active(self):
        return self.filter(is_deleted__in=[False])

    def marketing_visible(self, user):
        return self.active().filter(created_by=user)

    def pending_approval(self):
        return self.active().filter(is_superadmin_approved=False)

    def search(self, term):
        if not term:
            return self.active()
        return self.active().filter(
            models.Q(job_id_customer__icontains=term)
            | models.Q(system_id__icontains=term)
        )


class Job(models.Model):
    """Represents the marketing team's job drop."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jobs"
    )
    job_id_customer = models.CharField(
        "Job ID (From Customer)", max_length=64, unique=True
    )
    system_id = models.CharField(max_length=32, unique=True, editable=False)
    instruction = models.TextField(max_length=10000)
    amount_inr = models.DecimalField(max_digits=12, decimal_places=2)
    expected_deadline = models.DateTimeField()
    strict_deadline = models.DateTimeField()
    status = models.CharField(
        max_length=32, choices=JobStatus.choices, default=JobStatus.NEW
    )
    is_superadmin_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="deleted_jobs",
        on_delete=models.SET_NULL,
    )
    deleted_at = models.DateTimeField(blank=True, null=True)
    deletion_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="updated_jobs",
        on_delete=models.SET_NULL,
    )

    objects = JobQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.job_id_customer} ({self.system_id})"

    def clean(self):
        minimum_gap = timedelta(hours=24)
        if self.expected_deadline and self.strict_deadline:
            if self.strict_deadline <= self.expected_deadline:
                raise ValidationError(
                    "Strict deadline must be after expected deadline."
                )
            if self.strict_deadline - self.expected_deadline < minimum_gap:
                raise ValidationError(
                    "Strict deadline must be at least 24 hours later."
                )

            expected_date = self.expected_deadline.date()
            strict_date = self.strict_deadline.date()
            if Holiday.objects.filter(date=expected_date).exists():
                raise ValidationError("Expected deadline falls on a holiday.")
            if Holiday.objects.filter(date=strict_date).exists():
                raise ValidationError("Strict deadline falls on a holiday.")

    def save(self, *args, **kwargs):
        if not self.system_id:
            self.system_id = generate_system_id()
        super().save(*args, **kwargs)
        ensure_sections_for_job(self)

    def mark_deleted(self, user, notes=""):
        self.is_deleted = True
        self.deleted_by = user
        self.deletion_notes = notes
        self.deleted_at = timezone.now()
        self.save(
            update_fields=[
                "is_deleted",
                "deleted_by",
                "deletion_notes",
                "deleted_at",
                "updated_at",
            ]
        )

    def restore(self):
        self.is_deleted = False
        self.deleted_by = None
        self.deleted_at = None
        self.deletion_notes = ""
        self.save(
            update_fields=[
                "is_deleted",
                "deleted_by",
                "deleted_at",
                "deletion_notes",
                "updated_at",
            ]
        )


class JobAttachment(models.Model):
    """File uploads per job (doc, pdf, png, etc.)."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="attachments/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=512, blank=True)

    def __str__(self):
        return f"{self.job.system_id} attachment"


class JobContentSection(models.Model):
    """Stores generated content for each section (summary, structure, etc.)."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="sections")
    section_type = models.CharField(max_length=32, choices=ContentSectionType.choices)
    content = models.TextField(blank=True)
    status = models.CharField(
        max_length=32, choices=ContentStatus.choices, default=ContentStatus.WAITING
    )
    regeneration_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("job", "section_type")
        ordering = ("section_type",)

    def __str__(self):
        return f"{self.job.system_id} - {self.get_section_type_display()}"

    def can_regenerate(self):
        return self.regeneration_count < 3

    def add_history(self, action="regenerate"):
        """Persist the current content before overwriting it."""
        if not self.content:
            return
        JobContentSectionHistory.objects.create(
            section=self,
            action=action,
            content=self.content,
        )


def generate_system_id():
    """Generate system ID like JN-<timestamp>."""

    timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    return f"JN-{timestamp}"


def ensure_sections_for_job(job):
    """Create default content sections once a job is saved."""

    for section_value, _ in ContentSectionType.choices:
        JobContentSection.objects.get_or_create(job=job, section_type=section_value)


class JobContentSectionHistory(models.Model):
    """History of generated content per section."""

    section = models.ForeignKey(
        JobContentSection, on_delete=models.CASCADE, related_name="histories"
    )
    action = models.CharField(max_length=32, blank=True, default="regenerate")
    content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"History for {self.section} at {self.created_at}"
