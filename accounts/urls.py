"""URL patterns for authentication + profile flows."""

from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.SignupView.as_view(), name="signup"),
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("floor-signup/", views.FloorSignupView.as_view(), name="floor_signup"),
    path("floor-login/", views.FloorLoginView.as_view(), name="floor_login"),
    path("floor-signup/status/<str:token>/", views.FloorSignupStatusView.as_view(), name="floor_signup_status"),
    path("floor-status-lookup/", views.FloorStatusLookupView.as_view(), name="floor_status_lookup"),
    path("global-sso/start/", views.GlobalSSOStartView.as_view(), name="global_sso_start"),
    # Accept both with and without trailing slash to avoid redirect_uri mismatch
    path("global-sso/callback/", views.GlobalSSOCallbackView.as_view(), name="global_sso_callback"),
    path("global-sso/callback", views.GlobalSSOCallbackView.as_view()),
    path(
        "logout/",
        LogoutView.as_view(next_page="accounts:login"),
        name="logout",
    ),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path(
        "profile/update-request/",
        views.ProfileUpdateRequestView.as_view(),
        name="profile_update_request",
    ),
    path("pending/", views.email_verification_pending, name="pending"),
]
