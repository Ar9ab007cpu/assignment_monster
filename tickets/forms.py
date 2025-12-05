"""Forms for ticket creation and management."""

from django import forms
from django.utils import timezone

from accounts.models import User
from formbuilder.utils import apply_schema_to_form
from jobs.choices import JobStatus
from jobs.models import Holiday, Job
from .models import Ticket, TicketCategory, TicketStatus


class TicketCreateForm(forms.ModelForm):
    category = forms.ChoiceField(
        choices=TicketCategory.choices,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_category"}),
    )
    job = forms.ModelChoiceField(
        queryset=Job.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Related Job",
        help_text="Select the job that requires a change (for deadline change tickets).",
    )

    class Meta:
        model = Ticket
        fields = [
            "subject",
            "description",
            "category",
            "job",
            "requested_expected_deadline",
            "requested_strict_deadline",
        ]
        widgets = {
            "subject": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "requested_expected_deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
            "requested_strict_deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        initial_job = kwargs.pop("initial_job", None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields["job"].queryset = Job.objects.filter(
                created_by=self.user,
                is_deleted__in=[False],
                status__in=[JobStatus.NEW, JobStatus.IN_PROGRESS],
            ).order_by("-created_at")
        if initial_job:
            self.fields["job"].initial = initial_job
        apply_schema_to_form(self, "ticket_create", getattr(self.user, "role", None))

    def clean(self):
        data = super().clean()
        category = data.get("category")
        job = data.get("job")
        expected = data.get("requested_expected_deadline")
        strict = data.get("requested_strict_deadline")
        if category == TicketCategory.DEADLINE_CHANGE:
            if not job:
                self.add_error("job", "Select the job you need updated.")
            elif self.user and job.created_by != self.user:
                self.add_error("job", "You can only request changes for your jobs.")
            if job and job.status == JobStatus.COMPLETED:
                self.add_error("job", "Completed jobs cannot be changed.")
            if not expected or not strict:
                self.add_error(
                    "requested_expected_deadline",
                    "Provide both expected and strict deadlines for deadline change requests.",
                )
            else:
                if strict <= expected:
                    self.add_error(
                        "requested_strict_deadline",
                        "Strict deadline must be later than expected deadline.",
                    )
                elif strict - expected < timezone.timedelta(hours=24):
                    self.add_error(
                        "requested_strict_deadline",
                        "Strict deadline must be at least 24 hours after expected deadline.",
                    )
                expected_date = timezone.localtime(expected).date()
                strict_date = timezone.localtime(strict).date()
                if Holiday.objects.filter(date=expected_date).exists():
                    self.add_error(
                        "requested_expected_deadline",
                        "Expected deadline falls on a holiday.",
                    )
                if Holiday.objects.filter(date=strict_date).exists():
                    self.add_error(
                        "requested_strict_deadline",
                        "Strict deadline falls on a holiday.",
                    )
        else:
            data["job"] = None
            data["requested_expected_deadline"] = None
            data["requested_strict_deadline"] = None
        return data

    def save(self, commit=True, user=None):
        ticket = super().save(commit=False)
        if user:
            ticket.created_by = user
            ticket.reported_by_name = (user.get_full_name() or user.email or "").strip()
            ticket.reported_by_email = user.email or ""
        if commit:
            ticket.save()
        return ticket


class TicketResolveForm(forms.ModelForm):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Ticket
        fields = ["status", "assigned_to", "resolution_notes"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "resolution_notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 4}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(
            role__in=[User.Role.SUPER_ADMIN, User.Role.CO_SUPER_ADMIN]
        )
        self.fields["assigned_to"].label = "Assign to"
