"""Helpers to adapt forms using DB-backed schemas."""

from django import forms

from accounts.models import User
from .models import FormDefinition, FormField


ROLE_CHOICES = [
    User.Role.MARKETING,
    User.Role.SUPER_ADMIN,
    User.Role.CO_SUPER_ADMIN,
    User.Role.FLOOR,
]


def get_form_fields(slug, role):
    try:
        definition = (
            FormDefinition.objects.filter(slug=slug, is_active=True).order_by("pk").first()
        )
    except Exception:
        return []
    if not definition:
        return []
    fields = list(definition.fields.order_by("order", "id"))
    if role:
        fields = [f for f in fields if f.is_visible_for(role)]
    return fields


def apply_schema_to_form(form, slug, role):
    """Hide/show/require fields in a given form instance based on schema."""

    role_for_schema = role
    if role == User.Role.FLOOR:
        role_for_schema = User.Role.MARKETING

    fields = get_form_fields(slug, role_for_schema)
    if not fields:
        return
    # Ensure ordering based on schema
    ordered_names = [f.target_field for f in fields]

    # Build lookup keyed by target_field
    by_target = {f.target_field: f for f in fields}
    remove_keys = []
    for name, field in form.fields.items():
        meta = by_target.get(name)
        if not meta:
            continue
        # Visibility
        if not meta.is_visible_for(role_for_schema):
            remove_keys.append(name)
            continue
        # Required toggle
        field.required = meta.is_required_for(role_for_schema)
        # Read-only
        if meta.read_only_roles and role_for_schema in meta.read_only_roles:
            field.widget.attrs["readonly"] = True
            field.widget.attrs["disabled"] = True
    for key in remove_keys:
        form.fields.pop(key, None)
    # Reorder fields to match schema order
    try:
        from collections import OrderedDict

        new_fields = OrderedDict()
        for name in ordered_names:
            if name in form.fields:
                new_fields[name] = form.fields[name]
        # append any remaining fields
        for name, field in form.fields.items():
            if name not in new_fields:
                new_fields[name] = field
        form.fields = new_fields
    except Exception:
        pass


def choices_for_roles():
    return [
        (User.Role.MARKETING, "Marketing"),
        (User.Role.SUPER_ADMIN, "Super Admin"),
        (User.Role.CO_SUPER_ADMIN, "Co Super Admin"),
        (User.Role.FLOOR, "Floor"),
    ]
