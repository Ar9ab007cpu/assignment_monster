from django import forms

from accounts.models import User
from .models import FormField, FormDefinition
from .utils import choices_for_roles


ROLE_CHOICES = choices_for_roles()


class FormFieldForm(forms.ModelForm):
    visible_roles = forms.MultipleChoiceField(
        required=False,
        choices=ROLE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    required_roles = forms.MultipleChoiceField(
        required=False,
        choices=ROLE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    read_only_roles = forms.MultipleChoiceField(
        required=False,
        choices=ROLE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = FormField
        fields = [
            "name",
            "label",
            "help_text",
            "field_type",
            "order",
            "target_field",
            "visible_roles",
            "required_roles",
            "read_only_roles",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.is_system:
            self.fields["field_type"].disabled = True
            self.fields["order"].widget.attrs["readonly"] = True
            self.fields["name"].disabled = True
            self.fields["target_field"].disabled = True
