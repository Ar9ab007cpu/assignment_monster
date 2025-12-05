"""Forms dedicated to the marketing team."""

from datetime import timedelta

from django import forms
from django.utils import timezone

from jobs.models import Holiday, Job, JobAttachment
from formbuilder.utils import apply_schema_to_form


class JobDropForm(forms.ModelForm):
    attachments = forms.FileField(
        widget=forms.ClearableFileInput(attrs={"multiple": True}),
        required=False,
        help_text="Doc, Docx, PDF, PNG, JPG, JPEG, PPTX, CSV, XLSX, XLX",
    )

    class Meta:
        model = Job
        fields = [
            "job_id_customer",
            "instruction",
            "amount_inr",
            "expected_deadline",
            "strict_deadline",
        ]
        widgets = {
            "instruction": forms.Textarea(attrs={"rows": 5}),
            "expected_deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local"}
            ),
            "strict_deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local"}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", "form-control")
            elif isinstance(field.widget, forms.DateTimeInput):
                field.widget.attrs.setdefault("class", "form-control")
            elif isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs.setdefault("class", "form-control")
            else:
                field.widget.attrs.setdefault("class", "form-control")
        if self.user:
            apply_schema_to_form(self, "job_drop", getattr(self.user, "role", None))

    def clean(self):
        data = super().clean()
        expected = data.get("expected_deadline")
        strict = data.get("strict_deadline")
        if expected and strict:
            if strict <= expected:
                self.add_error(
                    "strict_deadline",
                    "Strict deadline must be greater than expected deadline.",
                )
            elif strict - expected < timedelta(hours=24):
                self.add_error(
                    "strict_deadline",
                    "Strict deadline must be at least 24 hours after expected deadline.",
                )
            expected_date = timezone.localtime(expected).date()
            strict_date = timezone.localtime(strict).date()
            if Holiday.objects.filter(date=expected_date).exists():
                self.add_error(
                    "expected_deadline",
                    "Expected deadline falls on a holiday. Please choose another date.",
                )
            if Holiday.objects.filter(date=strict_date).exists():
                self.add_error(
                    "strict_deadline",
                    "Strict deadline falls on a holiday. Please choose another date.",
                )
        return data

    def save(self, commit=True):
        job = super().save(commit=False)
        if self.user:
            job.created_by = self.user
        if commit:
            job.save()
            ip = ""
            ua = ""
            if self.request:
                meta = getattr(self.request, "META", {})
                ip = meta.get("REMOTE_ADDR") or ""
                ua = meta.get("HTTP_USER_AGENT") or ""
            ua = ua or "Unknown"
            for file in self.files.getlist("attachments"):
                JobAttachment.objects.create(
                    job=job,
                    file=file,
                    uploaded_ip=ip,
                    user_agent=ua,
                )
        return job
