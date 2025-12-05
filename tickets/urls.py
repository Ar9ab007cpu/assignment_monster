"""URLconf for ticketing."""

from django.urls import path

from . import views

app_name = "tickets"

urlpatterns = [
    path("", views.TicketListView.as_view(), name="my_tickets"),
    path("create/", views.TicketCreateView.as_view(), name="create_ticket"),
    path(
        "admin/history/",
        views.AdminTicketListView.as_view(),
        name="admin_history",
    ),
    path(
        "admin/<int:pk>/",
        views.AdminTicketDetailView.as_view(),
        name="admin_ticket_detail",
    ),
]
