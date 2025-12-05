from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import ProfileUpdateRequest, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    model = User
    list_display = (
        "email",
        "first_name",
        "last_name",
        "role",
        "employee_id",
        "is_account_approved",
    )
    list_filter = ("role", "is_account_approved")
    ordering = ("email",)
    search_fields = ("email", "first_name", "last_name", "employee_id")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "profile_picture",
                    "whatsapp_country_code",
                    "whatsapp_number",
                    "last_qualification",
                    "employee_id",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_account_approved",
                    "is_profile_verified",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "role"),
            },
        ),
    )


@admin.register(ProfileUpdateRequest)
class ProfileUpdateRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "request_type", "status", "created_at")
    list_filter = ("request_type", "status")
    search_fields = ("user__email", "user__first_name", "user__last_name")
