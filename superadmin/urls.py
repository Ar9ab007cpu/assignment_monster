"""Super Admin URL patterns."""

from django.urls import path

from . import views

app_name = "superadmin"

urlpatterns = [
    path("welcome/", views.WelcomeView.as_view(), name="welcome"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("all-jobs/", views.AllJobsView.as_view(), name="all_jobs"),
    path("new-jobs/", views.NewJobsView.as_view(), name="new_jobs"),
    path("deleted-jobs/", views.DeletedJobsView.as_view(), name="deleted_jobs"),
    path("job/<int:pk>/", views.JobDetailView.as_view(), name="job_detail"),
    path("job/<int:pk>/delete/", views.JobDeleteView.as_view(), name="job_delete"),
    path("job/<int:pk>/restore/", views.JobRestoreView.as_view(), name="job_restore"),
    path(
        "job/<int:pk>/deadline/",
        views.JobDeadlineUpdateView.as_view(),
        name="job_deadline_edit",
    ),
    path("section-action/", views.JobSectionActionView.as_view(), name="section_action"),
    path("user-approval/", views.UserApprovalView.as_view(), name="user_approval"),
    path("global-users/", views.GlobalUserManagementView.as_view(), name="global_users"),
    path(
        "profile-update-requests/",
        views.ProfileRequestListView.as_view(),
        name="profile_update_requests",
    ),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path(
        "management-hub/",
        views.ManagementHubView.as_view(),
        name="management_hub",
    ),
    path(
        "holidays/",
        views.HolidayManagementView.as_view(),
        name="holiday_management",
    ),
    path(
        "forms/<slug:slug>/",
        views.FormManagementView.as_view(),
        name="form_management",
    ),
    path(
        "forms/",
        views.FormManagementListView.as_view(),
        name="form_management_list",
    ),
    path(
        "navigation/",
        views.NavigationOrderView.as_view(),
        name="navigation_order",
    ),
    path(
        "user-activity/",
        views.UserActivityView.as_view(),
        name="user_activity",
    ),
    path(
        "system-control/",
        views.ManagementSystemControlView.as_view(),
        name="system_control",
    ),
    path(
        "notice-management/",
        views.NoticeManagementView.as_view(),
        name="notice_management",
    ),
    path(
        "coupon-management/",
        views.CouponManagementView.as_view(),
        name="coupon_management",
    ),
    path(
        "activity-logs/",
        views.ActivityLogView.as_view(),
        name="activity_logs",
    ),
    path(
        "error-logs/",
        views.ErrorLogView.as_view(),
        name="error_logs",
    ),
    path(
        "floor-signups/",
        views.FloorSignupRequestListView.as_view(),
        name="floor_signup_requests",
    ),
    path(
        "log-restore/",
        views.LogRestoreView.as_view(),
        name="log_restore",
    ),
    path(
        "attachments/",
        views.AttachmentAuditView.as_view(),
        name="attachment_audit",
    ),
]
