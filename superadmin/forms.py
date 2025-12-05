"""Forms for Super Admin actions."""

from django import forms
from django.utils import timezone

from common.models import ManagementSystem
from accounts.models import User
from jobs.models import Holiday, Job


class JobSectionActionForm(forms.Form):
    section_id = forms.IntegerField(widget=forms.HiddenInput)
    action = forms.ChoiceField(
        choices=[
            ("regenerate", "Regenerate"),
            ("approve", "Approve"),
            ("monster", "Monster"),
        ],
        widget=forms.HiddenInput,
    )


class UserApprovalActionForm(forms.Form):
    user_id = forms.IntegerField(widget=forms.HiddenInput)
    decision = forms.ChoiceField(
        choices=[("approve", "Approve"), ("reject", "Reject")],
        widget=forms.HiddenInput,
    )


class ProfileRequestActionForm(forms.Form):
    request_id = forms.IntegerField(widget=forms.HiddenInput)
    decision = forms.ChoiceField(
        choices=[("approve", "Approve"), ("reject", "Reject")],
        widget=forms.HiddenInput,
    )
    notes = forms.CharField(required=False, widget=forms.HiddenInput)


class ManagementSystemForm(forms.ModelForm):
    class Meta:
        model = ManagementSystem
        fields = [
            "id",
            "description",
            "enabled_for_accounts",
            "enabled_for_marketing",
            "enabled_for_superadmins",
        ]
        widgets = {
            "id": forms.HiddenInput(),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Notes"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        switch_fields = [
            "enabled_for_accounts",
            "enabled_for_marketing",
            "enabled_for_superadmins",
        ]
        for field_name in switch_fields:
            field = self.fields[field_name]
            field.widget.attrs.setdefault("class", "form-check-input")
            field.label = "Enabled"


class UserManagementActionForm(forms.Form):
    user_id = forms.IntegerField(widget=forms.HiddenInput)
    role = forms.ChoiceField(
        choices=User.Role.choices,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ["date", "description"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean(self):
        data = super().clean()
        date = data.get("date")
        if not date:
            return data
        qs = Holiday.objects.filter(date=date)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            self.add_error("date", "A holiday already exists for this date.")
        return data


class JobDeadlineForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = ["expected_deadline", "strict_deadline"]
        widgets = {
            "expected_deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
            "strict_deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
        }

    def clean(self):
        data = super().clean()
        job = self.instance
        expected = data.get("expected_deadline")
        strict = data.get("strict_deadline")
        if expected and strict:
            if strict <= expected:
                self.add_error(
                    "strict_deadline",
                    "Strict deadline must be greater than expected deadline.",
                )
            elif strict - expected < timezone.timedelta(hours=24):
                self.add_error(
                    "strict_deadline",
                    "Strict deadline must be at least 24 hours after expected deadline.",
                )
            expected_date = timezone.localtime(expected).date()
            strict_date = timezone.localtime(strict).date()
            if Holiday.objects.filter(date=expected_date).exists():
                self.add_error(
                    "expected_deadline",
                    "Expected deadline falls on a holiday.",
                )
            if Holiday.objects.filter(date=strict_date).exists():
                self.add_error(
                    "strict_deadline",
                    "Strict deadline falls on a holiday.",
                )
            if job and job.pk and job.strict_deadline == strict and job.expected_deadline == expected:
                self.add_error(
                    None,
                    "No changes detected in deadlines.",
                )
        return data
