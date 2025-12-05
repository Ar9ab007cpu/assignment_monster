"""URLconf for page builder management."""

from django.urls import path

from . import views

app_name = "pagebuilder"

urlpatterns = [
    path("", views.PageTemplateListView.as_view(), name="templates"),
    path("themes/new/", views.ThemeCreateView.as_view(), name="theme_create"),
    path("animations/new/", views.AnimationCreateView.as_view(), name="animation_create"),
    path("<int:pk>/", views.PageTemplateEditView.as_view(), name="edit_template"),
]
