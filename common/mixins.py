"""Reusable mixins for enforcing management system toggles."""

from django.contrib import messages
from django.shortcuts import redirect

from .system_control import get_system_name, is_system_enabled


class ManagementSystemGateMixin:
    """Redirects users if the configured management system is disabled."""

    management_system_key = None
    management_system_message = "The {system} is currently disabled by Super Admin."

    def get_management_system_denied_redirect(self):
        return redirect("common:welcome")

    def dispatch(self, request, *args, **kwargs):
        if self.management_system_key and not is_system_enabled(
            self.management_system_key, request.user
        ):
            system_name = get_system_name(self.management_system_key)
            messages.error(
                request,
                self.management_system_message.format(system=system_name),
            )
            return self.get_management_system_denied_redirect()
        return super().dispatch(request, *args, **kwargs)
