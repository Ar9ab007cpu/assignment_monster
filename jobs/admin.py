from django.contrib import admin

from .models import Job, JobAttachment, JobContentSection


class JobAttachmentInline(admin.TabularInline):
    model = JobAttachment
    extra = 0


class JobContentSectionInline(admin.TabularInline):
    model = JobContentSection
    extra = 0


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = (
        "job_id_customer",
        "system_id",
        "created_by",
        "amount_inr",
        "expected_deadline",
        "strict_deadline",
        "is_superadmin_approved",
        "is_deleted",
    )
    list_filter = ("is_superadmin_approved", "status", "is_deleted")
    search_fields = ("job_id_customer", "system_id")
    inlines = [JobAttachmentInline, JobContentSectionInline]
