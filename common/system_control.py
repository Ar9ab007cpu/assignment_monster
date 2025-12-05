"""Helpers to query management system configuration."""

from django.core.exceptions import ObjectDoesNotExist

from accounts.models import User
from .models import ManagementSystem

ROLE_FIELD_MAP = {
    "anonymous": "enabled_for_accounts",
    User.Role.MARKETING: "enabled_for_marketing",
    User.Role.SUPER_ADMIN: "enabled_for_superadmins",
    User.Role.CO_SUPER_ADMIN: "enabled_for_superadmins",
}


def _field_for_user(user):
    if user and getattr(user, "is_authenticated", False):
        return ROLE_FIELD_MAP.get(user.role, "enabled_for_accounts")
    return ROLE_FIELD_MAP["anonymous"]


def is_system_enabled(key, user=None):
    """Return True if the system is enabled for the provided user."""

    try:
        system = ManagementSystem.objects.get(key=key)
    except ObjectDoesNotExist:
        return True
    return getattr(system, _field_for_user(user))


def get_management_system_map(user=None):
    """Return metadata + enabled flag per system for templates."""

    field = _field_for_user(user)
    data = {
        choice: {
            "name": label,
            "description": "",
            "enabled": True,
        }
        for choice, label in ManagementSystem.Keys.choices
    }
    systems = ManagementSystem.objects.all()
    for system in systems:
        data[system.key] = {
            "name": system.name,
            "description": system.description,
            "enabled": getattr(system, field),
        }
    return data


def get_system_name(key):
    try:
        return ManagementSystem.objects.get(key=key).name
    except ObjectDoesNotExist:
        return "Requested feature"
