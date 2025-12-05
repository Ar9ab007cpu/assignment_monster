from django.urls import path
from . import views

app_name = "common"

urlpatterns = [
    path("notice/dismiss/", views.dismiss_notice, name="dismiss_notice"),
    path("", views.root_redirect, name="welcome"),
]
