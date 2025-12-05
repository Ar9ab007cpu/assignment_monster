from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include(("common.urls", "common"), namespace="common")),
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("marketing/", include(("marketing.urls", "marketing"), namespace="marketing")),
    path("superadmin/", include(("superadmin.urls", "superadmin"), namespace="superadmin")),
    path("jobs/", include(("jobs.urls", "jobs"), namespace="jobs")),
    path("tickets/", include(("tickets.urls", "tickets"), namespace="tickets")),
    path("pagebuilder/", include(("pagebuilder.urls", "pagebuilder"), namespace="pagebuilder")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
