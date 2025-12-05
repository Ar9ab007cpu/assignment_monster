"""Forms shared across job workflows."""

from django import forms

from formbuilder.utils import apply_schema_to_form

class JobDeleteForm(forms.Form):
    notes = forms.CharField(
        label="Deletion Notes",
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        help_text="Explain why this job is being removed.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_schema_to_form(self, "job_delete", None)
