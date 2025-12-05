"""Ticket views for all roles."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.core.paginator import Paginator
from django.db import models
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from accounts.models import User
from common.mixins import ManagementSystemGateMixin
from common.models import ManagementSystem
from jobs.choices import JobStatus
from jobs.models import Job
from .forms import TicketCreateForm, TicketResolveForm
from .models import Ticket, TicketCategory, TicketStatus


class TicketAccessMixin(ManagementSystemGateMixin, LoginRequiredMixin):
    management_system_key = ManagementSystem.Keys.TICKETS


class TicketAdminAccessMixin(
    ManagementSystemGateMixin, LoginRequiredMixin, UserPassesTestMixin
):
    management_system_key = ManagementSystem.Keys.TICKETS

    def test_func(self):
        return self.request.user.role in {
            User.Role.SUPER_ADMIN,
            User.Role.CO_SUPER_ADMIN,
        }

    def handle_no_permission(self):
        messages.error(self.request, "You need Super Admin rights to manage tickets.")
        return redirect("common:welcome")


class TicketListView(TicketAccessMixin, TemplateView):
    template_name = "tickets/my_tickets.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tickets = Ticket.objects.filter(created_by=self.request.user)
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            tickets = tickets.filter(
                models.Q(ticket_id__icontains=search_query)
                | models.Q(subject__icontains=search_query)
                | models.Q(description__icontains=search_query)
                | models.Q(category__icontains=search_query)
                | models.Q(job__job_id_customer__icontains=search_query)
                | models.Q(job__system_id__icontains=search_query)
                | models.Q(resolution_notes__icontains=search_query)
            )
        paginator = Paginator(tickets, 10)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["tickets"] = page_obj
        context["page_obj"] = page_obj
        context["paginator"] = paginator
        context["search_query"] = search_query
        context["status_choices"] = TicketStatus.choices
        return context


class TicketCreateView(TicketAccessMixin, FormView):
    template_name = "tickets/create_ticket.html"
    form_class = TicketCreateForm
    success_url = reverse_lazy("tickets:my_tickets")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        job_id = self.request.GET.get("job")
        if job_id:
            try:
                kwargs["initial_job"] = Job.objects.get(
                    pk=job_id, created_by=self.request.user
                )
            except Job.DoesNotExist:
                pass
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        category = self.request.GET.get("category")
        if category in dict(TicketCategory.choices):
            initial["category"] = category
        job_id = self.request.GET.get("job")
        if job_id:
            initial["job"] = job_id
        return initial

    def form_valid(self, form):
        form.save(user=self.request.user)
        messages.success(self.request, "Ticket raised successfully.")
        return super().form_valid(form)


class AdminTicketListView(TicketAdminAccessMixin, TemplateView):
    template_name = "tickets/admin_ticket_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tickets = Ticket.objects.select_related("created_by", "assigned_to", "job")
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            tickets = tickets.filter(
                models.Q(ticket_id__icontains=search_query)
                | models.Q(subject__icontains=search_query)
                | models.Q(description__icontains=search_query)
                | models.Q(created_by__email__icontains=search_query)
                | models.Q(created_by__first_name__icontains=search_query)
                | models.Q(created_by__last_name__icontains=search_query)
                | models.Q(job__job_id_customer__icontains=search_query)
                | models.Q(job__system_id__icontains=search_query)
                | models.Q(category__icontains=search_query)
            )
        paginator = Paginator(tickets, 10)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["tickets"] = page_obj
        context["page_obj"] = page_obj
        context["paginator"] = paginator
        context["search_query"] = search_query
        context["status_counts"] = {
            status: Ticket.objects.filter(status=status).count()
            for status, _ in TicketStatus.choices
        }
        return context


class AdminTicketDetailView(TicketAdminAccessMixin, FormView):
    template_name = "tickets/admin_ticket_detail.html"
    form_class = TicketResolveForm

    def dispatch(self, request, *args, **kwargs):
        self.ticket = get_object_or_404(Ticket, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.ticket
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ticket"] = self.ticket
        context["related_job"] = self.ticket.job
        return context

    def form_valid(self, form):
        new_status = form.cleaned_data["status"]
        ticket = form.save(commit=False)
        if new_status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
            ticket.assigned_to = self.request.user
        else:
            ticket.assigned_to = form.cleaned_data.get("assigned_to")
        ticket.save()
        messages.success(
            self.request,
            "Ticket updated and marked as resolved."
            if new_status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}
            else "Ticket status updated.",
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("tickets:admin_history")
