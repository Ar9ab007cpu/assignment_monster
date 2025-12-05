"""Marketing URL patterns."""

from django.urls import path

from . import views

app_name = "marketing"

urlpatterns = [
    path("analyze/", views.GlobalAnalyzeView.as_view(), name="analyze"),
    path("global/summary/", views.GlobalSummaryView.as_view(), name="global_summary"),
    path("global/structure/", views.GlobalStructureView.as_view(), name="global_structure"),
    path("global/content/", views.GlobalContentView.as_view(), name="global_content"),
    path("global/referencing/", views.GlobalReferencingView.as_view(), name="global_referencing"),
    path("global/plag/", views.GlobalPlagView.as_view(), name="global_plag"),
    path("global/ai/", views.GlobalAIView.as_view(), name="global_ai"),
    path("global/full/", views.GlobalFullView.as_view(), name="global_full"),
    path("global/monster/", views.GlobalMonsterView.as_view(), name="global_monster"),
    path("global/coupons/", views.GlobalCouponsView.as_view(), name="global_coupons"),
    path("global/notices/", views.GlobalNoticeListView.as_view(), name="global_notices"),
    path("job/<int:pk>/section/<slug:section>/", views.SectionDetailView.as_view(), name="section_detail"),
    path("global-home/", views.GlobalDashboardView.as_view(), name="global_home"),
    path("global-history/", views.GlobalGemsHistoryView.as_view(), name="global_history"),
    path("global-profile/edit/", views.GlobalProfileEditView.as_view(), name="global_profile_edit"),
    path("welcome/", views.MarketingWelcomeView.as_view(), name="welcome"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("all-projects/", views.AllProjectsView.as_view(), name="all_projects"),
    path("history/", views.HistoryView.as_view(), name="history"),
    path("holidays/", views.HolidayListView.as_view(), name="holidays"),
    path("deleted-jobs/", views.DeletedJobsView.as_view(), name="deleted_jobs"),
    path("create-job/", views.JobDropView.as_view(), name="create_job"),
    path("job/<int:pk>/", views.JobDetailView.as_view(), name="job_detail"),
    path("section-action/", views.MarketingSectionActionView.as_view(), name="section_action"),
    path("job/<int:pk>/delete/", views.MarketingJobDeleteView.as_view(), name="job_delete"),
]
