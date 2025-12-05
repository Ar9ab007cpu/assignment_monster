from django import forms

from .models import AnimationPreset, PageBlock, PageTemplate, Theme


class ThemeForm(forms.ModelForm):
    class Meta:
        model = Theme
        fields = [
            "name",
            "primary_color",
            "secondary_color",
            "accent_color",
            "background",
            "font_family",
            "base_font_size",
            "spacing_scale",
            "radius",
            "shadow",
            "animation",
            "is_active",
        ]
        widgets = {
            "spacing_scale": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. [4,8,12,16,24,32]",
                }
            ),
        }


class PageTemplateForm(forms.ModelForm):
    class Meta:
        model = PageTemplate
        fields = [
            "slug",
            "name",
            "description",
            "theme",
            "allowed_roles",
            "managed_by_roles",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }


class PageBlockForm(forms.ModelForm):
    class Meta:
        model = PageBlock
        fields = [
            "block_type",
            "area",
            "order",
            "title",
            "data",
            "style",
            "animation",
            "is_active",
        ]
        widgets = {
            "data": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "style": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }


class AnimationPresetForm(forms.ModelForm):
    class Meta:
        model = AnimationPreset
        fields = [
            "name",
            "css_class",
            "duration_ms",
            "easing",
            "delay_ms",
        ]
