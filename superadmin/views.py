"""Views powering the Super Admin experience."""

import datetime
import csv
import io

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.cache import cache
from django.db import models
from django.db.models import Q
from django.forms import modelformset_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, TemplateView
from django.http import HttpResponse

from decimal import Decimal
try:
    from bson.decimal128 import Decimal128
    from bson.objectid import ObjectId
except Exception:
    Decimal128 = None
    ObjectId = None
try:
    from bson.decimal128 import Decimal128
except Exception:
    Decimal128 = None
from accounts.models import ProfileUpdateRequest, User, GemsAccount, GemTransaction
from accounts.views import ensure_gems_account
from common.mixins import ManagementSystemGateMixin
from common.models import (
    ManagementSystem,
    Notice,
    ActivityLog,
    ErrorLog,
    ActivityLogArchive,
    ErrorLogArchive,
    Coupon,
    CouponRedemption,
)
from accounts.models import User, FloorSignupRequest
from common.utils import format_currency, to_decimal
from jobs.choices import ContentSectionType, ContentStatus, JobStatus
from jobs.forms import JobDeleteForm
from jobs.models import Holiday, Job, JobContentSection, JobAttachment
from jobs.services import (
    get_job_cards_for_user,
    normalize_amount,
    sync_job_approval,
    generate_job_summary,
    generate_structure_from_summary,
    generate_content_from_structure,
    generate_references_from_content,
    generate_final_document_with_citations,
)
from marketing.models import AnalyzeHistory, StructureHistory, ContentHistory, MonsterHistory
from marketing.views import (
    get_section_cost,
    get_monster_cost,
    SECTION_GEM_COST_DEFAULTS,
    MONSTER_GEM_COST_DEFAULT,
)
from common.models import GemCostRule

import csv
from django.http import HttpResponse

from formbuilder.forms import FormFieldForm
from formbuilder.models import FormDefinition, FormField
try:
    from navbuilder.models import NavigationItem
except Exception:
    NavigationItem = None
from .forms import (
    HolidayForm,
    JobDeadlineForm,
    JobSectionActionForm,
    ManagementSystemForm,
    ProfileRequestActionForm,
    UserApprovalActionForm,
    UserManagementActionForm,
)


SECTION_SEQUENCE = [
    ContentSectionType.SUMMARY,
    ContentSectionType.STRUCTURE,
    ContentSectionType.CONTENT,
    ContentSectionType.REFERENCING,
    ContentSectionType.PLAG_REPORT,
    ContentSectionType.AI_REPORT,
    ContentSectionType.FULL_CONTENT,
]


class SuperAdminAccessMixin(
    ManagementSystemGateMixin, LoginRequiredMixin, UserPassesTestMixin
):
    """Restrict views to super admin accounts."""

    management_system_key = None

    def test_func(self):
        return self.request.user.role in {
            User.Role.SUPER_ADMIN,
            User.Role.CO_SUPER_ADMIN,
        }

    def handle_no_permission(self):
        messages.error(self.request, "Super Admin access required.")
        return redirect("common:welcome")


class WelcomeView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/welcome.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cards"] = get_job_cards_for_user(self.request.user)
        start, end = self._get_date_range()
        start_dt, end_dt = self._get_datetime_bounds(start, end)
        jobs = Job.objects.filter(
            is_deleted__in=[False],
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        )
        context["chart_data"] = self._build_chart_data(jobs, start, end)
        context["start_date"] = start
        context["end_date"] = end
        return context

    def _get_date_range(self):
        today = timezone.localdate()
        try:
            start_str = self.request.GET.get("start")
            end_str = self.request.GET.get("end")
            start = datetime.date.fromisoformat(start_str) if start_str else None
            end = datetime.date.fromisoformat(end_str) if end_str else None
        except Exception:
            start = end = None
        if not end:
            end = today
        if not start or start > end:
            start = end - datetime.timedelta(days=29)
        return start, end

    def _get_datetime_bounds(self, start, end):
        tz = timezone.get_current_timezone()
        start_dt = datetime.datetime.combine(start, datetime.time.min)
        end_dt = datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min)
        return timezone.make_aware(start_dt, tz), timezone.make_aware(end_dt, tz)

    def _build_chart_data(self, jobs, start, end):
        day_count = (end - start).days + 1
        labels = [(start + datetime.timedelta(days=i)) for i in range(day_count)]
        job_counts = {d: 0 for d in labels}
        job_amounts = {d: normalize_amount(0) for d in labels}
        for job in jobs:
            day = job.created_at.date()
            if day in job_counts:
                job_counts[day] += 1
                job_amounts[day] += normalize_amount(job.amount_inr)

        counts_series = [job_counts[d] for d in labels]
        amounts_series = [float(job_amounts[d]) for d in labels]

        avg_count = sum(counts_series) / len(counts_series) if counts_series else 0
        avg_amount = sum(amounts_series) / len(amounts_series) if amounts_series else 0
        next_labels = [end + datetime.timedelta(days=i + 1) for i in range(30)]
        next_counts = [round(avg_count, 2)] * 30
        next_amounts = [round(avg_amount, 2)] * 30

        return {
            "labels": [d.isoformat() for d in labels],
            "counts": counts_series,
            "amounts": amounts_series,
            "next_labels": [d.isoformat() for d in next_labels],
            "next_counts": next_counts,
            "next_amounts": next_amounts,
        }


class DashboardView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/dashboard.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def _stage_label(self, job):
        """Return human-readable stage based on section progress."""
        if job.status == JobStatus.COMPLETED or job.is_superadmin_approved:
            return "Completed"
        section_map = {section.section_type: section for section in job.sections.all()}
        for section_type in SECTION_SEQUENCE:
            section = section_map.get(section_type)
            if not section:
                label = dict(ContentSectionType.choices).get(section_type, section_type)
                return f"{label} (Not started)"
            if section.status != ContentStatus.APPROVED:
                return f"{section.get_section_type_display()} ({section.get_status_display()})"
        return "Awaiting final approval"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cards"] = get_job_cards_for_user(self.request.user)
        jobs = list(Job.objects.filter(is_deleted__in=[False]).order_by("-created_at"))
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            jobs = [
                job
                for job in jobs
                if search_query.lower() in (job.job_id_customer or "").lower()
                or search_query.lower() in (job.system_id or "").lower()
                or search_query.lower() in (job.instruction or "").lower()
            ]
        recent_jobs = jobs[:5]
        for job in recent_jobs:
            job.stage_label = self._stage_label(job)
        context["recent_jobs"] = recent_jobs
        context["jobs_page_obj"] = None
        context["jobs_paginator"] = None
        context["search_query"] = search_query
        pending_users = [
            user
            for user in User.objects.filter(role=User.Role.MARKETING)
            if user.is_active and not user.is_account_approved
        ]
        context["pending_users"] = len(pending_users)
        context["pending_profile_requests"] = len(
            [
                req
                for req in ProfileUpdateRequest.objects.all()
                if req.status == ProfileUpdateRequest.Status.PENDING
            ]
        )
        return context


class AllJobsView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/all_jobs.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def _parse_date(self, value):
        try:
            return datetime.date.fromisoformat(value)
        except Exception:
            return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        default_start = today - datetime.timedelta(days=29)
        start_raw = (self.request.GET.get("start") or "").strip()
        end_raw = (self.request.GET.get("end") or "").strip()
        start_date = self._parse_date(start_raw) or default_start
        end_date = self._parse_date(end_raw) or today
        if end_date < start_date:
            end_date = start_date
        start_dt = timezone.make_aware(
            datetime.datetime.combine(start_date, datetime.time.min),
            timezone.get_current_timezone(),
        )
        end_dt = timezone.make_aware(
            datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min),
            timezone.get_current_timezone(),
        )

        jobs = list(
            Job.objects.filter(
                is_deleted__in=[False],
                created_at__gte=start_dt,
                created_at__lt=end_dt,
            )
        )
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            q = search_query.lower()
            jobs = [
                job
                for job in jobs
                if q in (job.job_id_customer or "").lower()
                or q in (job.system_id or "").lower()
                or q in (job.instruction or "").lower()
                or q in (job.created_by.get_full_name() or "").lower()
                or q in (job.created_by.email or "").lower()
            ]
        def category_for(job):
            any_section_approved = job.sections.filter(
                status=ContentStatus.APPROVED
            ).exists()
            if job.status == JobStatus.COMPLETED or job.is_superadmin_approved:
                return "completed"
            if job.status == JobStatus.IN_PROGRESS or any_section_approved:
                return "in_progress"
            return "new"

        category_filter = self.request.GET.get("category", "all")
        if category_filter != "all":
            jobs = [job for job in jobs if category_for(job) == category_filter]

        for job in jobs:
            job.section_map = {
                section.section_type: section for section in job.sections.all()
            }
        paginator = Paginator(jobs, 5)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["jobs"] = page_obj
        context["jobs_page_obj"] = page_obj
        context["jobs_paginator"] = paginator
        context["section_sequence"] = SECTION_SEQUENCE
        context["cards"] = get_job_cards_for_user(self.request.user)
        context["search_query"] = search_query
        context["category"] = category_filter
        base_jobs = list(Job.objects.filter(is_deleted__in=[False]))
        context["category_counts"] = {
            "new": len([j for j in base_jobs if category_for(j) == "new"]),
            "in_progress": len([j for j in base_jobs if category_for(j) == "in_progress"]),
            "completed": len([j for j in base_jobs if category_for(j) == "completed"]),
        }
        context["start_date"] = start_date
        context["end_date"] = end_date
        base_query = self.request.GET.copy()
        if "page" in base_query:
            base_query.pop("page")
        context["base_query"] = base_query.urlencode()
        return context


class UserActivityView(SuperAdminAccessMixin, TemplateView):
    """View user activity (jobs and amounts) within a date range."""

    template_name = "superadmin/user_activity.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def _safe_amount(self, value):
        try:
            return to_decimal(value)
        except Exception:
            if Decimal128 and isinstance(value, Decimal128):
                try:
                    return to_decimal(value.to_decimal())
                except Exception:
                    try:
                        return Decimal(str(value))
                    except Exception:
                        return Decimal("0")
            try:
                return Decimal(str(value))
            except Exception:
                return Decimal("0")

    def _parse_date(self, value):
        try:
            return datetime.date.fromisoformat(value)
        except Exception:
            return None

    def _export_csv(self, day_rows, filename="user_activity.csv", extras=None):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        if extras and "metrics" in extras:
            writer.writerow(["Metric", "Total"])
            for label, value in extras["metrics"]:
                writer.writerow([label, value])
            writer.writerow([])
        writer.writerow(["Date", "Activity/Jobs", "Amount"])
        for row in day_rows:
            writer.writerow([row["day"].isoformat(), row["total_jobs"], row["total_amount"]])
        if extras and "totals" in extras:
            writer.writerow([])
            writer.writerow(["Totals", extras["totals"].get("jobs", 0), extras["totals"].get("amount", 0)])
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role_choices = [
            User.Role.MARKETING,
            User.Role.GLOBAL,
            User.Role.SUPER_ADMIN,
            User.Role.CO_SUPER_ADMIN,
        ]
        role_filter = (self.request.GET.get("role") or "").strip().lower()
        if role_filter not in role_choices:
            role_filter = User.Role.MARKETING  # default so page isn't empty

        user_query = ""
        users_qs = User.objects.none()
        if role_filter:
            users_qs = User.objects.filter(role=role_filter).order_by("email")

        user_id = self.request.GET.get("user") or ""
        start_str = self.request.GET.get("start") or ""
        end_str = self.request.GET.get("end") or ""

        start_date = self._parse_date(start_str)
        end_date = self._parse_date(end_str)
        if start_date and end_date and end_date < start_date:
            end_date = start_date
        if not start_date or not end_date:
            end_date = end_date or timezone.localdate()
            start_date = start_date or (end_date - datetime.timedelta(days=29))

        selected_user = None
        if role_filter:
            if user_id:
                selected_user = users_qs.filter(pk=user_id).first()
            if not selected_user:
                selected_user = users_qs.first()

        # If no user available for the chosen role, show empty state
        if not selected_user:
            context.update(
                users=users_qs,
                selected_user=None,
                role_filter=role_filter,
                role_choices=role_choices,
                user_query=user_query,
                start_date=start_date,
                end_date=end_date,
                total_jobs=0,
                total_amount=0,
                day_rows=[],
                chart_labels=[],
                chart_jobs=[],
                chart_amounts=[],
                word_count_total=None,
                analyze_count=None,
                structure_count=None,
                content_count=None,
                monster_count=None,
                completed_jobs_count=None,
            )
            return context

        jobs = Job.objects.filter(is_deleted__in=[False])
        jobs = jobs.filter(created_by=selected_user)
        # Avoid DB-specific __date casts; use datetime bounds instead.
        start_dt = timezone.make_aware(
            datetime.datetime.combine(start_date, datetime.time.min),
            timezone.get_current_timezone(),
        )
        end_dt = timezone.make_aware(
            datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min),
            timezone.get_current_timezone(),
        )
        jobs = jobs.filter(created_at__gte=start_dt, created_at__lt=end_dt)

        # Group per day in Python to avoid backend-specific date casts
        day_map = {}
        for job in jobs:
            day = job.created_at.date()
            stats = day_map.setdefault(day, {"total_jobs": 0, "total_amount": 0})
            stats["total_jobs"] += 1
            try:
                amount_val = job.amount_inr
            except Exception:
                amount_val = getattr(job, "amount_inr", 0)
            stats["total_amount"] += float(self._safe_amount(amount_val))
        grouped = [
            {"day": day, "total_jobs": data["total_jobs"], "total_amount": data["total_amount"]}
            for day, data in sorted(day_map.items())
        ]

        labels = [item["day"].isoformat() for item in grouped]
        job_counts = [item["total_jobs"] for item in grouped]
        amount_series = [float(self._safe_amount(item["total_amount"])) for item in grouped]

        # Word count only for marketing/floor users
        word_count_total = None
        word_roles = {User.Role.MARKETING}
        if hasattr(User.Role, "FLOOR"):
            word_roles.add(User.Role.FLOOR)
        if selected_user and selected_user.role in word_roles:
            try:
                sections = JobContentSection.objects.filter(job__in=jobs)
                word_count_total = sum(len((section.content or "").split()) for section in sections)
            except Exception:
                word_count_total = None

        # Extra metrics per role
        analyze_count = structure_count = content_count = monster_count = None
        completed_jobs_count = None
        total_gems_spent = None
        gems_day_map = {}
        analyze_day_map = {}
        structure_day_map = {}
        content_day_map = {}
        monster_day_map = {}
        if selected_user and selected_user.role == User.Role.GLOBAL:
            analyze_count = structure_count = content_count = monster_count = 0
            try:
                analyze_count = AnalyzeHistory.objects.filter(
                    user=selected_user, created_at__gte=start_dt, created_at__lt=end_dt
                ).count()
                structure_count = StructureHistory.objects.filter(
                    user=selected_user, created_at__gte=start_dt, created_at__lt=end_dt
                ).count()
                content_count = ContentHistory.objects.filter(
                    user=selected_user, created_at__gte=start_dt, created_at__lt=end_dt
                ).count()
                monster_count = MonsterHistory.objects.filter(
                    user=selected_user, created_at__gte=start_dt, created_at__lt=end_dt
                ).count()
            except Exception:
                pass
            try:
                gems_txs = GemTransaction.objects.filter(user=selected_user, created_at__gte=start_dt, created_at__lt=end_dt)
                spent = Decimal("0")
                for tx in gems_txs:
                    amt = to_decimal(getattr(tx, "amount", 0))
                    if amt < 0:
                        spent += abs(amt)
                        day = tx.created_at.date()
                        gems_day_map[day] = gems_day_map.get(day, Decimal("0")) + abs(amt)
                total_gems_spent = spent
            except Exception:
                total_gems_spent = None
            try:
                for row in AnalyzeHistory.objects.filter(user=selected_user, created_at__gte=start_dt, created_at__lt=end_dt):
                    d = row.created_at.date()
                    analyze_day_map[d] = analyze_day_map.get(d, 0) + 1
                for row in StructureHistory.objects.filter(user=selected_user, created_at__gte=start_dt, created_at__lt=end_dt):
                    d = row.created_at.date()
                    structure_day_map[d] = structure_day_map.get(d, 0) + 1
                for row in ContentHistory.objects.filter(user=selected_user, created_at__gte=start_dt, created_at__lt=end_dt):
                    d = row.created_at.date()
                    content_day_map[d] = content_day_map.get(d, 0) + 1
                for row in MonsterHistory.objects.filter(user=selected_user, created_at__gte=start_dt, created_at__lt=end_dt):
                    d = row.created_at.date()
                    monster_day_map[d] = monster_day_map.get(d, 0) + 1
            except Exception:
                analyze_day_map = structure_day_map = content_day_map = monster_day_map = {}
            # If no jobs, build daily rows from global activity maps + gems
            if not grouped:
                all_days = set(gems_day_map.keys()) | set(analyze_day_map.keys()) | set(structure_day_map.keys()) | set(content_day_map.keys()) | set(monster_day_map.keys())
                grouped = []
                for day in sorted(all_days):
                    total_actions = analyze_day_map.get(day, 0) + structure_day_map.get(day, 0) + content_day_map.get(day, 0) + monster_day_map.get(day, 0)
                    grouped.append(
                        {
                            "day": day,
                            "total_jobs": total_actions,
                            "total_amount": float(self._safe_amount(gems_day_map.get(day, 0))),
                        }
                    )
                labels = [item["day"].isoformat() for item in grouped]
                job_counts = [item["total_jobs"] for item in grouped]
                amount_series = [float(self._safe_amount(item["total_amount"])) for item in grouped]
        if selected_user and selected_user.role in word_roles:
            try:
                completed_jobs_count = Job.objects.filter(
                    created_by=selected_user,
                    status=JobStatus.COMPLETED,
                    created_at__gte=start_dt,
                    created_at__lt=end_dt,
                    is_deleted__in=[False],
                ).count()
            except Exception:
                completed_jobs_count = None

        # Build display rows (recent 5 days)
        display_rows = sorted(grouped, key=lambda x: x["day"], reverse=True)[:5]
        display_rows.sort(key=lambda x: x["day"])
        total_jobs_sum = sum(item["total_jobs"] for item in grouped)
        total_amount_sum = sum(self._safe_amount(item["total_amount"]) for item in grouped)

        context.update(
            users=users_qs,
            selected_user=selected_user,
            role_filter=role_filter,
            role_choices=role_choices,
            user_query=user_query,
            start_date=start_date,
            end_date=end_date,
            total_jobs=jobs.count(),
            total_amount=sum(self._safe_amount(getattr(job, "amount_inr", 0)) for job in jobs),
            day_rows=display_rows,
            full_day_rows=grouped,
            total_jobs_sum=total_jobs_sum,
            total_amount_sum=total_amount_sum,
            chart_labels=labels,
            chart_jobs=job_counts,
            chart_amounts=amount_series,
            word_count_total=word_count_total,
            analyze_count=analyze_count,
            structure_count=structure_count,
            content_count=content_count,
            monster_count=monster_count,
            completed_jobs_count=completed_jobs_count,
            total_gems_spent=total_gems_spent,
            gems_chart_labels=[d.isoformat() for d in sorted(gems_day_map.keys())],
            gems_chart_values=[float(gems_day_map[d]) for d in sorted(gems_day_map.keys())],
            analyze_chart_labels=[d.isoformat() for d in sorted(analyze_day_map.keys())],
            analyze_chart_values=[analyze_day_map[d] for d in sorted(analyze_day_map.keys())],
            structure_chart_labels=[d.isoformat() for d in sorted(structure_day_map.keys())],
            structure_chart_values=[structure_day_map[d] for d in sorted(structure_day_map.keys())],
            content_chart_labels=[d.isoformat() for d in sorted(content_day_map.keys())],
            content_chart_values=[content_day_map[d] for d in sorted(content_day_map.keys())],
            monster_chart_labels=[d.isoformat() for d in sorted(monster_day_map.keys())],
            monster_chart_values=[monster_day_map[d] for d in sorted(monster_day_map.keys())],
        )
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get("export") == "csv":
            user_name = "user"
            selected_user = context.get("selected_user")
            if selected_user:
                user_name = (selected_user.get_full_name() or selected_user.email or "user").replace(" ", "_")
            filename = f"{user_name}_activity.csv"
            extras = None
            totals = {
                "jobs": context.get("total_jobs_sum") or 0,
                "amount": context.get("total_amount_sum") or 0,
            }
            if selected_user and selected_user.role == User.Role.GLOBAL:
                extras = {
                    "metrics": [
                        ("Total Gems Spent", context.get("total_gems_spent") or 0),
                        ("Analyze Documents", context.get("analyze_count") or 0),
                        ("Structure Generations", context.get("structure_count") or 0),
                        ("Content Generations", context.get("content_count") or 0),
                        ("Monster Clicks", context.get("monster_count") or 0),
                    ],
                    "totals": totals,
                }
            else:
                extras = {"totals": totals}
            return self._export_csv(context.get("full_day_rows", []), filename=filename, extras=extras)
        return super().render_to_response(context, **response_kwargs)

class NewJobsView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/new_jobs.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def _category_for(self, job):
        any_section_approved = job.sections.filter(status=ContentStatus.APPROVED).exists()
        if job.status == JobStatus.COMPLETED or job.is_superadmin_approved:
            return "completed"
        if job.status == JobStatus.IN_PROGRESS or any_section_approved:
            return "in_progress"
        return "new"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_qs = Job.objects.filter(is_deleted__in=[False])
        jobs = [job for job in base_qs if self._category_for(job) == "new"]
        for job in jobs:
            job.section_map = {
                section.section_type: section for section in job.sections.all()
            }
        pending_jobs = len(jobs)
        total_amount = sum(normalize_amount(job.amount_inr) for job in jobs)
        context["cards"] = [
            {"title": "Total New Jobs", "value": pending_jobs, "url": ""},
            {"title": "Total Amount", "value": format_currency(total_amount), "url": ""},
        ]
        self.request.session["seen_superadmin_new_jobs"] = pending_jobs

        paginator = Paginator(jobs, 5)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["jobs"] = page_obj
        context["jobs_page_obj"] = page_obj
        context["jobs_paginator"] = paginator
        context["section_sequence"] = SECTION_SEQUENCE
        return context


class DeletedJobsView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/deleted_jobs.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        jobs = [
            job
            for job in Job.objects.all()
            if job.is_deleted
        ]
        jobs.sort(key=lambda job: job.deleted_at or timezone.now(), reverse=True)
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            q = search_query.lower()
            jobs = [
                job
                for job in jobs
                if q in (job.job_id_customer or "").lower()
                or q in (job.system_id or "").lower()
                or q in (job.instruction or "").lower()
                or q in (job.created_by.get_full_name() or "").lower()
            ]
        context["jobs"] = jobs
        context["search_query"] = search_query
        return context


class JobDeleteView(SuperAdminAccessMixin, FormView):
    template_name = "superadmin/job_delete.html"
    form_class = JobDeleteForm
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def dispatch(self, request, *args, **kwargs):
        job_id = kwargs["pk"]
        self.job = Job.objects.filter(pk=job_id, is_deleted__in=[False]).first()
        if not self.job:
            messages.error(request, "Job not found or already deleted.")
            return redirect("superadmin:deleted_jobs")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["job"] = self.job
        return context

    def form_valid(self, form):
        self.job.mark_deleted(self.request.user, form.cleaned_data["notes"])
        messages.info(self.request, "Job deleted and moved to Deleted Jobs.")
        return redirect("superadmin:deleted_jobs")


class JobRestoreView(SuperAdminAccessMixin, View):
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT
    def post(self, request, *args, **kwargs):
        jobs = [job for job in Job.objects.all() if job.is_deleted]
        job = next((job for job in jobs if job.pk == int(kwargs["pk"])), None)
        if not job:
            raise Http404("Job not found or already active")
        job.restore()
        messages.success(request, "Job restored successfully.")
        if job.status == JobStatus.NEW and not job.is_superadmin_approved:
            return redirect("superadmin:new_jobs")
        return redirect("superadmin:all_jobs")


class JobDetailView(SuperAdminAccessMixin, DetailView):
    template_name = "superadmin/job_detail.html"
    model = Job
    context_object_name = "job"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job = context["job"]
        visited = set(self.request.session.get("visited_job_ids", []))
        if job.pk not in visited:
            visited.add(job.pk)
            self.request.session["visited_job_ids"] = list(visited)
        sections = []
        for section_value in SECTION_SEQUENCE:
            section = job.sections.filter(section_type=section_value).first()
            if section:
                sections.append(section)
        context["sections"] = sections
        context["attachments"] = job.attachments.all()
        return context


class JobSectionActionView(SuperAdminAccessMixin, View):
    """Handle regenerate / approve section actions."""

    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    AI_PLAG_SET = {
        ContentSectionType.AI_REPORT,
        ContentSectionType.PLAG_REPORT,
    }

    def _previous_section_approved(self, section):
        sequence = list(SECTION_SEQUENCE)
        if section.section_type not in sequence:
            return True
        idx = sequence.index(section.section_type)
        if idx == 0:
            return True
        prev_type = sequence[idx - 1]
        prev_section = section.job.sections.filter(section_type=prev_type).first()
        return prev_section and prev_section.status == ContentStatus.APPROVED

    def _generate_section_content(self, section, regenerate=False):
        job = section.job
        if section.section_type == ContentSectionType.SUMMARY:
            return generate_job_summary(job, regenerate=regenerate, exceeded=not section.can_regenerate())
        if section.section_type == ContentSectionType.STRUCTURE:
            return generate_structure_from_summary(job, regenerate=regenerate, exceeded=not section.can_regenerate())
        if section.section_type == ContentSectionType.CONTENT:
            return generate_content_from_structure(job, regenerate=regenerate, exceeded=not section.can_regenerate())
        if section.section_type == ContentSectionType.REFERENCING:
            return generate_references_from_content(job, regenerate=regenerate, exceeded=not section.can_regenerate())
        if section.section_type == ContentSectionType.FULL_CONTENT:
            return generate_final_document_with_citations(job, regenerate=regenerate, exceeded=not section.can_regenerate())
        return section.content

    def post(self, request, *args, **kwargs):
        form = JobSectionActionForm(request.POST)
        redirect_url = request.META.get("HTTP_REFERER") or reverse("superadmin:new_jobs")
        if not form.is_valid():
            messages.error(request, "Invalid action.")
            return redirect(redirect_url)

        section = get_object_or_404(
            JobContentSection, pk=form.cleaned_data["section_id"]
        )
        action = form.cleaned_data["action"]

        # Pipeline gating
        if action in {"approve", "regenerate"} and not self._previous_section_approved(
            section
        ):
            messages.error(
                request,
                "Previous section must be approved before processing this one.",
            )
            return redirect(redirect_url)

        if action == "regenerate":
            if section.section_type in self.AI_PLAG_SET:
                section.content = "AI/Plag Report not available."
                section.status = ContentStatus.REGENERATE
                section.save(update_fields=["content", "status", "updated_at"])
                sync_job_approval(section.job)
                messages.warning(request, "AI/Plag Report not available.")
            elif not section.can_regenerate():
                messages.error(request, "Regeneration limit reached.")
            else:
                section.content = self._generate_section_content(section, regenerate=True)
                section.regeneration_count += 1
                section.status = ContentStatus.REGENERATE
                section.save(
                    update_fields=["content", "regeneration_count", "status", "updated_at"]
                )
                sync_job_approval(section.job)
                messages.success(
                    request,
                    f"Section regenerated. (attempt {section.regeneration_count} of 3)",
                )
        elif action == "approve":
            if section.section_type in self.AI_PLAG_SET:
                section.status = ContentStatus.APPROVED
                section.save(update_fields=["status", "updated_at"])
                sync_job_approval(section.job)
                messages.success(request, "Section approved.")
            else:
                if not section.content:
                    section.content = self._generate_section_content(section, regenerate=False)
                section.status = ContentStatus.APPROVED
                section.save(update_fields=["content", "status", "updated_at"])
                sync_job_approval(section.job)
                messages.success(request, "Section approved.")
        else:
            messages.error(request, "Unknown action.")

        return redirect(redirect_url)


class UserApprovalView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/user_approval.html"
    management_system_key = ManagementSystem.Keys.USER

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "approval")
        if action == "manage":
            form = UserManagementActionForm(request.POST)
            if form.is_valid():
                target = get_object_or_404(User, pk=form.cleaned_data["user_id"])
                if (
                    request.user.role == User.Role.CO_SUPER_ADMIN
                    and target.role == User.Role.SUPER_ADMIN
                ):
                    messages.error(
                        request,
                        "Co Super Admins cannot modify Super Admin accounts.",
                    )
                    return redirect("superadmin:user_approval")
                desired_role = form.cleaned_data["role"]
                if (
                    request.user.role == User.Role.CO_SUPER_ADMIN
                    and desired_role == User.Role.SUPER_ADMIN
                ):
                    messages.error(
                        request,
                        "Co Super Admins cannot assign the Super Admin role.",
                    )
                    return redirect("superadmin:user_approval")
                target.role = desired_role
                target.is_active = form.cleaned_data["is_active"]
                target.save(update_fields=["role", "is_active"])
                messages.success(request, f"{target.get_full_name()} updated.")
            else:
                messages.error(request, "Invalid user update submission.")
        else:
            form = UserApprovalActionForm(request.POST)
            if form.is_valid():
                user = get_object_or_404(User, pk=form.cleaned_data["user_id"])
                decision = form.cleaned_data["decision"]
                if decision == "approve":
                    user.is_account_approved = True
                    user.is_active = True
                    user.save()
                    messages.success(request, f"{user.get_full_name()} approved.")
                else:
                    user.is_account_approved = False
                    user.is_active = False
                    user.save()
                    messages.info(request, f"{user.get_full_name()} rejected.")
            else:
                messages.error(request, "Invalid submission.")
        return redirect("superadmin:user_approval")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        users_qs = User.objects.all().order_by("date_joined")
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            users_qs = users_qs.filter(
                models.Q(first_name__icontains=search_query)
                | models.Q(last_name__icontains=search_query)
                | models.Q(email__icontains=search_query)
                | models.Q(employee_id__icontains=search_query)
            )
        paginator = Paginator(users_qs, 5)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        users = list(page_obj.object_list)
        current_role = self.request.user.role
        for account in users:
            account.can_manage = (
                current_role == User.Role.SUPER_ADMIN
                or account.role != User.Role.SUPER_ADMIN
            )
        pending_users = [
            user
            for user in users
            if user.role == User.Role.MARKETING
            and not user.is_account_approved
            and user.is_active
        ]
        context["pending_users"] = pending_users
        context["user_search_query"] = search_query
        total_pending = len(pending_users)
        total_approved = len([user for user in users if user.is_account_approved])
        total_rejected = len(
            [
                user
                for user in users
                if not user.is_active and not user.is_account_approved
            ]
        )
        context["cards"] = [
            {
                "title": "Total User Request",
                "value": total_approved + total_rejected,
                "badge": total_pending,
            },
            {
                "title": "Total Approved User",
                "value": total_approved,
            },
            {
                "title": "Total Rejected User",
                "value": total_rejected,
            },
            {
                "title": "Pending Action",
                "value": total_pending,
            },
        ]
        context["all_users"] = users
        context["all_users_page"] = page_obj
        context["all_users_paginator"] = paginator
        context["role_choices"] = User.Role.choices
        context["can_assign_super_admin"] = (
            self.request.user.role == User.Role.SUPER_ADMIN
        )
        self.request.session["seen_superadmin_user_approvals"] = total_pending
        return context


class GlobalUserManagementView(SuperAdminAccessMixin, TemplateView):
    """Manage global users and recharge gems."""

    template_name = "superadmin/global_users.html"

    def _coerce_decimal(self, value):
        if value is None:
            return Decimal("0")
        if Decimal128 and isinstance(value, Decimal128):
            return value.to_decimal()
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "update_costs":
            updates = {
                GemCostRule.Keys.SUMMARY: request.POST.get("cost_summary"),
                GemCostRule.Keys.STRUCTURE: request.POST.get("cost_structure"),
                GemCostRule.Keys.CONTENT: request.POST.get("cost_content"),
                GemCostRule.Keys.MONSTER: request.POST.get("cost_monster"),
            }
            for key, raw in updates.items():
                if raw is None or raw == "":
                    continue
                try:
                    val = Decimal(str(raw))
                    GemCostRule.objects.update_or_create(key=key, defaults={"cost": val})
                except Exception:
                    messages.error(request, f"Invalid cost value for {key}.")
                    return redirect("superadmin:global_users")
            messages.success(request, "Gem cost rules updated.")
            return redirect("superadmin:global_users")

        user_id = request.POST.get("user_id")
        user_email = request.POST.get("user_email", "").strip().lower()
        amount = request.POST.get("amount")
        reason = request.POST.get("reason", "Admin recharge")
        try:
            amount_dec = Decimal(amount)
        except Exception:
            messages.error(request, "Invalid amount.")
            return redirect("superadmin:global_users")
        target = None
        if user_email:
            target = User.objects.filter(email__iexact=user_email, role=User.Role.GLOBAL).first()
        if not target and user_id:
            try:
                target = User.objects.filter(pk=int(user_id), role=User.Role.GLOBAL).first()
            except Exception:
                target = User.objects.filter(pk=user_id, role=User.Role.GLOBAL).first()
        if not target:
            messages.error(request, "Global user not found.")
            return redirect("superadmin:global_users")
        # normalize and de-dup the user's gems account
        account = ensure_gems_account(target, "Admin recharge")
        current_dec = self._coerce_decimal(account.balance)
        account.balance = current_dec + amount_dec
        account.save()
        GemTransaction.objects.create(
            user=target,
            amount=amount_dec,
            reason=reason or "Admin recharge",
            created_by=request.user,
        )
        messages.success(
            request, f"Added {amount_dec} gems to {target.get_full_name() or target.email}."
        )
        return redirect("superadmin:global_users")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        globals_qs = User.objects.filter(role=User.Role.GLOBAL).order_by("email")
        rows = []
        for u in globals_qs:
            account = ensure_gems_account(u, "Welcome bonus")
            rows.append(
                {
                    "user": u,
                    "balance": account.balance,
                    "latest": GemTransaction.objects.filter(user=u).first(),
                }
            )
        context["global_users"] = rows
        context["gem_cost_rules"] = [
            ("Summary generation", get_section_cost(ContentSectionType.SUMMARY)),
            ("Structure generation", get_section_cost(ContentSectionType.STRUCTURE)),
            ("Content (per 200 words)", get_section_cost(ContentSectionType.CONTENT)),
            ("Monster generation", get_monster_cost()),
        ]
        context["gem_cost_defaults"] = {
            "summary": SECTION_GEM_COST_DEFAULTS.get(ContentSectionType.SUMMARY, Decimal("0")),
            "structure": SECTION_GEM_COST_DEFAULTS.get(ContentSectionType.STRUCTURE, Decimal("0")),
            "content": SECTION_GEM_COST_DEFAULTS.get(ContentSectionType.CONTENT, Decimal("0")),
            "monster": MONSTER_GEM_COST_DEFAULT,
        }
        return context


class ProfileRequestListView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/profile_update_requests.html"
    management_system_key = ManagementSystem.Keys.PROFILE

    def post(self, request, *args, **kwargs):
        form = ProfileRequestActionForm(request.POST)
        if form.is_valid():
            prof_request = get_object_or_404(
                ProfileUpdateRequest, pk=form.cleaned_data["request_id"]
            )
            decision = form.cleaned_data["decision"]
            notes = form.cleaned_data.get("notes", "")
            if decision == "approve":
                prof_request.approve(request.user, notes=notes)
                messages.success(request, "Request approved.")
            else:
                prof_request.reject(request.user, notes=notes)
                messages.info(request, "Request rejected.")
        else:
            messages.error(request, "Invalid submission.")
        return redirect("superadmin:profile_update_requests")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        requests_qs = ProfileUpdateRequest.objects.select_related("user").order_by(
            "-created_at"
        )
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            requests_qs = requests_qs.filter(
                models.Q(user__first_name__icontains=search_query)
                | models.Q(user__last_name__icontains=search_query)
                | models.Q(user__email__icontains=search_query)
                | models.Q(user__employee_id__icontains=search_query)
                | models.Q(request_type__icontains=search_query)
                | models.Q(status__icontains=search_query)
                | models.Q(updated_value__icontains=search_query)
                | models.Q(current_value__icontains=search_query)
            )
        requests_list = list(requests_qs)
        paginator = Paginator(requests_list, 10)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["requests"] = page_obj
        context["requests_page"] = page_obj
        context["requests_paginator"] = paginator
        context["requests_search_query"] = search_query
        context["recent_requests"] = requests_list[:10]
        context["cards"] = [
            {
                "title": "Total Request",
                "value": len(requests_list),
            },
            {
                "title": "Total Pending Request",
                "value": len(
                    [
                        req
                        for req in requests_qs
                        if req.status == ProfileUpdateRequest.Status.PENDING
                    ]
                ),
            },
            {
                "title": "Total Approved",
                "value": len(
                    [
                        req
                        for req in requests_qs
                        if req.status == ProfileUpdateRequest.Status.APPROVED
                    ]
                ),
            },
            {
                "title": "Total Reject",
                "value": len(
                    [
                        req
                        for req in requests_qs
                        if req.status == ProfileUpdateRequest.Status.REJECTED
                    ]
                ),
            },
        ]
        pending_requests = len(
            [
                req
                for req in requests_qs
                if req.status == ProfileUpdateRequest.Status.PENDING
            ]
        )
        self.request.session["seen_superadmin_profile_requests"] = pending_requests
        return context


class ProfileView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/profile.html"
    management_system_key = ManagementSystem.Keys.PROFILE

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        requests_qs = ProfileUpdateRequest.objects.filter(user=user).order_by(
            "-created_at"
        )
        paginator = Paginator(requests_qs, 5)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["profile_requests"] = page_obj
        context["requests_paginator"] = paginator
        context["requests_page_obj"] = page_obj
        return context


class AttachmentAuditView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/attachment_audit.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def post(self, request, *args, **kwargs):
        attachment_id = request.POST.get("attachment_id")
        if attachment_id:
            attachment = JobAttachment.objects.filter(pk=attachment_id).first()
            if attachment:
                attachment.delete()
                messages.success(request, "Attachment deleted.")
            else:
                messages.error(request, "Attachment not found.")
        return redirect("superadmin:attachment_audit")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        attachments_qs = JobAttachment.objects.select_related("job", "job__created_by").order_by(
            "-uploaded_at"
        )
        paginator = Paginator(attachments_qs, 10)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["attachments"] = page_obj
        context["attachments_page"] = page_obj
        context["attachments_paginator"] = paginator
        context["total_files"] = attachments_qs.count()
        context["total_size"] = sum((att.file.size or 0) for att in attachments_qs)
        return context


class NoticeManagementView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/notice_management.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "create")
        if action == "expire":
            notice_id = request.POST.get("notice_id")
            notice = Notice.objects.filter(pk=notice_id).first()
            if notice:
                notice.delete()
                # refresh cache with remaining notices instead of clearing everything
                remaining = list(
                    Notice.objects.values(
                        "id",
                        "title",
                        "message",
                        "start_at",
                        "end_at",
                        "is_active",
                        "show_on_marketing",
                        "show_on_global",
                    )
                )
                cache.set("fallback_notices", remaining, None)
                messages.success(request, "Notice expired and removed.")
            else:
                messages.error(request, "Notice not found.")
            return redirect("superadmin:notice_management")

        # create/update
        notice_id = request.POST.get("notice_id")
        title = request.POST.get("title", "").strip()
        message = request.POST.get("message", "").strip()
        start_at = request.POST.get("start_at")
        end_at = request.POST.get("end_at")
        is_active = request.POST.get("is_active") == "on"
        show_on_marketing = request.POST.get("show_on_marketing") == "on"
        show_on_global = request.POST.get("show_on_global") == "on"
        def _parse(dt_str):
            if not dt_str:
                return None
            try:
                dt = datetime.datetime.fromisoformat(dt_str)
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.get_current_timezone())
                return dt
            except Exception:
                return None
        start_dt = _parse(start_at) or timezone.now()
        end_dt = _parse(end_at)
        if end_dt and end_dt < start_dt:
            end_dt = start_dt

        if not title or not message:
            messages.error(request, "Title and message are required.")
            return redirect("superadmin:notice_management")
        if not show_on_marketing and not show_on_global:
            messages.error(request, "Select at least one audience (Marketing or Global User).")
            return redirect("superadmin:notice_management")

        notice = Notice.objects.filter(pk=notice_id).first() if notice_id else Notice()
        notice.title = title
        notice.message = message
        notice.start_at = start_dt
        notice.end_at = end_dt
        notice.is_active = is_active
        notice.show_on_marketing = show_on_marketing
        notice.show_on_global = show_on_global
        if not notice.pk:
            notice.created_by = request.user
        notice.updated_by = request.user
        try:
            notice.save()
            # refresh fallback cache for situations where DB reads are blocked
            cache.set(
                "fallback_notices",
                list(
                    Notice.objects.values(
                        "id",
                        "title",
                        "message",
                        "start_at",
                        "end_at",
                        "is_active",
                        "show_on_marketing",
                        "show_on_global",
                    )
                ),
                None,
            )
            messages.success(request, "Notice saved.")
        except Exception as exc:
            messages.error(request, f"Could not save notice: {exc}")
        return redirect("superadmin:notice_management")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["notices"] = Notice.objects.all().order_by("-created_at")
        except Exception:
            cached = cache.get("fallback_notices", [])
            context["notices"] = cached
            if not cached:
                messages.error(self.request, "Could not load notices. Please ensure migrations are applied.")
        # paginate notices (5 per page)
        notices_list = context.get("notices", [])
        paginator = Paginator(notices_list, 5)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["notices_page"] = page_obj
        context["notices_paginator"] = paginator
        return context


class ActivityLogView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/activity_logs.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def get(self, request, *args, **kwargs):
        if request.GET.get("archive") == "1":
            return self._archive_logs()
        # Handle export
        qs, _, _ = self._filter_queryset(request)
        if request.GET.get("export") == "csv":
            return self._export_csv(qs)
        return super().get(request, *args, **kwargs)

    def _export_csv(self, qs):
        import csv
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="activity_logs.csv"'
        writer = csv.writer(response)
        writer.writerow(["Timestamp", "User", "Role", "Path", "Method", "Status", "IP", "Browser", "Duration (ms)", "Action", "Referrer"])
        for log in qs:
            user = log.user.get_full_name() if log.user else "Anonymous"
            role = getattr(log.user, "get_role_display", lambda: "")()
            writer.writerow([
                timezone.localtime(log.created_at).isoformat(),
                user,
                role,
                log.path,
                log.method,
                log.status_code,
                log.ip_address,
                log.user_agent,
                f"{log.duration_ms:.2f}",
                log.action_type,
                log.referrer,
            ])
        return response

    def _filter_queryset(self, request):
        qs = ActivityLog.objects.select_related("user").order_by("-created_at")
        start = request.GET.get("start")
        end = request.GET.get("end")
        user_id = request.GET.get("user")
        action = request.GET.get("action")
        q = request.GET.get("q", "").strip()

        if start:
            try:
                start_dt = datetime.datetime.fromisoformat(start)
                qs = qs.filter(created_at__gte=start_dt)
            except ValueError:
                pass
        if end:
            try:
                end_dt = datetime.datetime.fromisoformat(end)
                qs = qs.filter(created_at__lte=end_dt)
            except ValueError:
                pass
        if user_id:
            qs = qs.filter(user_id=user_id)
        if action:
            qs = qs.filter(action_type=action)
        if q:
            qs = qs.filter(
                models.Q(path__icontains=q)
                | models.Q(user_agent__icontains=q)
                | models.Q(referrer__icontains=q)
            )
        return qs, start, end

    def _archive_logs(self):
        """Export logs older than 30 days to CSV and delete them."""
        cutoff = timezone.now() - datetime.timedelta(days=30)
        old_qs = ActivityLog.objects.filter(created_at__lt=cutoff)
        if not old_qs.exists():
            messages.info(self.request, "No logs older than 30 days to archive.")
            return redirect("superadmin:activity_logs")
        # store in archive table
        archive_rows = [
            ActivityLogArchive(
                user=log.user,
                path=log.path,
                method=log.method,
                status_code=log.status_code,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                referrer=log.referrer,
                duration_ms=log.duration_ms,
                action_type=log.action_type,
                extra_meta=log.extra_meta,
                session_key=log.session_key,
                created_at=log.created_at,
            )
            for log in old_qs
        ]
        ActivityLogArchive.objects.bulk_create(archive_rows)
        # also provide CSV download
        import csv
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="activity_logs_archive.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Timestamp",
                "User",
                "Role",
                "Path",
                "Method",
                "Status",
                "IP",
                "Browser",
                "Duration (ms)",
                "Action",
                "Referrer",
            ]
        )
        for log in old_qs:
            user = log.user.get_full_name() if log.user else "Anonymous"
            role = getattr(log.user, "get_role_display", lambda: "")()
            writer.writerow(
                [
                    timezone.localtime(log.created_at).isoformat(),
                    user,
                    role,
                    log.path,
                    log.method,
                    log.status_code,
                    log.ip_address,
                    log.user_agent,
                    f"{log.duration_ms:.2f}",
                    log.action_type,
                    log.referrer,
                ]
            )
        # delete archived
        old_qs.delete()
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs, start, end = self._filter_queryset(self.request)
        paginator = Paginator(qs, 10)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["logs"] = page_obj
        context["logs_page_obj"] = page_obj
        context["logs_paginator"] = paginator
        # Limit page links to a window of 10 pages
        current = page_obj.number
        total_pages = paginator.num_pages
        start_page = max(1, current - 4)
        end_page = min(total_pages, start_page + 9)
        start_page = max(1, end_page - 9)
        context["logs_page_window"] = range(start_page, end_page + 1)
        context["users"] = User.objects.all().order_by("first_name")
        context["filters"] = {
            "start": start,
            "end": end,
            "user": self.request.GET.get("user", ""),
            "action": self.request.GET.get("action", ""),
            "q": self.request.GET.get("q", ""),
        }
        actions = ActivityLog.objects.exclude(action_type="").values_list("action_type", flat=True)
        context["action_types"] = sorted(set(actions) | {"request"})
        context["total_logs"] = qs.count()
        context["avg_duration"] = qs.aggregate(avg=models.Avg("duration_ms")).get("avg") or 0
        return context


class ErrorLogView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/error_logs.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def get(self, request, *args, **kwargs):
        if request.GET.get("archive") == "1":
            return self._archive_logs()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        log_id = request.POST.get("log_id")
        if not log_id:
            messages.error(request, "Missing log id.")
            return redirect("superadmin:error_logs")
        log = ErrorLog.objects.filter(pk=log_id).first()
        if not log:
            messages.error(request, "Log not found.")
            return redirect("superadmin:error_logs")
        if action == "resolve":
            log.resolved = True
            log.resolved_by = request.user
            log.resolved_at = timezone.now()
            log.save(update_fields=["resolved", "resolved_by", "resolved_at"])
            messages.success(request, "Marked as resolved.")
        elif action == "unresolve":
            log.resolved = False
            log.resolved_by = None
            log.resolved_at = None
            log.save(update_fields=["resolved", "resolved_by", "resolved_at"])
            messages.info(request, "Marked as unresolved.")
        elif action == "delete":
            ErrorLogArchive.objects.create(
                user=log.user,
                path=log.path,
                method=log.method,
                status_code=log.status_code,
                message=log.message,
                traceback=log.traceback,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                referrer=log.referrer,
                resolved=log.resolved,
                created_at=log.created_at,
            )
            log.delete()
            messages.success(request, "Log deleted.")
        else:
            messages.error(request, "Unknown action.")
        return redirect("superadmin:error_logs")

    def _filter_queryset(self, request):
        qs = ErrorLog.objects.select_related("user").order_by("-created_at")
        start = request.GET.get("start")
        end = request.GET.get("end")
        status = request.GET.get("status")
        q = request.GET.get("q", "").strip()

        if start:
            try:
                start_dt = datetime.datetime.fromisoformat(start)
                qs = qs.filter(created_at__gte=start_dt)
            except ValueError:
                pass
        if end:
            try:
                end_dt = datetime.datetime.fromisoformat(end)
                qs = qs.filter(created_at__lte=end_dt)
            except ValueError:
                pass
        if status == "resolved":
            qs = qs.filter(resolved=True)
        elif status == "open":
            qs = qs.filter(resolved=False)
        if q:
            qs = qs.filter(
                models.Q(path__icontains=q)
                | models.Q(message__icontains=q)
                | models.Q(traceback__icontains=q)
            )
        return qs, start, end

    def _archive_logs(self):
        """Export error logs older than 30 days to CSV and delete them."""
        cutoff = timezone.now() - datetime.timedelta(days=30)
        old_qs = ErrorLog.objects.filter(created_at__lt=cutoff)
        if not old_qs.exists():
            messages.info(self.request, "No error logs older than 30 days to archive.")
            return redirect("superadmin:error_logs")
        archive_rows = [
            ErrorLogArchive(
                user=log.user,
                path=log.path,
                method=log.method,
                status_code=log.status_code,
                message=log.message,
                traceback=log.traceback,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                referrer=log.referrer,
                resolved=log.resolved,
                created_at=log.created_at,
            )
            for log in old_qs
        ]
        ErrorLogArchive.objects.bulk_create(archive_rows)
        import csv
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="error_logs_archive.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Timestamp",
                "User",
                "Role",
                "Path",
                "Method",
                "Status",
                "Message",
                "IP",
                "Browser",
                "Referrer",
                "Resolved",
            ]
        )
        for log in old_qs:
            user = log.user.get_full_name() if log.user else "Anonymous"
            role = getattr(log.user, "get_role_display", lambda: "")()
            writer.writerow(
                [
                    timezone.localtime(log.created_at).isoformat(),
                    user,
                    role,
                    log.path,
                    log.method,
                    log.status_code,
                    log.message,
                    log.ip_address,
                    log.user_agent,
                    log.referrer,
                    "Yes" if log.resolved else "No",
                ]
            )
        old_qs.delete()
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            qs, start, end = self._filter_queryset(self.request)
            paginator = Paginator(qs, 10)
            page_number = self.request.GET.get("page")
            page_obj = paginator.get_page(page_number)
            context["logs"] = page_obj
            context["logs_page_obj"] = page_obj
            context["logs_paginator"] = paginator
            current = page_obj.number
            total_pages = paginator.num_pages
            start_page = max(1, current - 4)
            end_page = min(total_pages, start_page + 9)
            start_page = max(1, end_page - 9)
            context["logs_page_window"] = range(start_page, end_page + 1)
            context["filters"] = {
                "start": start,
                "end": end,
                "status": self.request.GET.get("status", ""),
                "q": self.request.GET.get("q", ""),
            }
            context["total_logs"] = qs.count()
            # show most recent traceback for preview
            context["latest_traceback"] = qs.first().traceback if qs else ""
        except Exception:
            context["logs"] = []
            context["logs_paginator"] = None
            context["logs_page_window"] = []
            messages.error(self.request, "Error log table unavailable. Please migrate.")
        return context


class LogRestoreView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/log_restore.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def post(self, request, *args, **kwargs):
        log_type = request.POST.get("log_type")
        uploaded = request.FILES.get("file")
        if log_type not in {"activity", "error"} or not uploaded:
            messages.error(request, "Please select log type and upload a CSV file.")
            return redirect("superadmin:log_restore")

        try:
            text = uploaded.read().decode("utf-8", errors="ignore")
            reader = csv.DictReader(io.StringIO(text))
        except Exception as exc:
            messages.error(request, f"Could not read CSV: {exc}")
            return redirect("superadmin:log_restore")

        created = 0
        failed = 0
        for row in reader:
            try:
                created += self._restore_row(log_type, row)
            except Exception:
                failed += 1
        if created:
            messages.success(request, f"Restored {created} {log_type} log(s).")
        if failed:
            messages.warning(request, f"Skipped {failed} row(s) due to errors.")
        return redirect("superadmin:log_restore")

    def _parse_ts(self, value):
        try:
            return datetime.datetime.fromisoformat(value)
        except Exception:
            return timezone.now()

    def _restore_row(self, log_type, row):
        if log_type == "activity":
            ActivityLog.objects.create(
                user=None,
                path=row.get("Path", "")[:512],
                method=row.get("Method", "")[:10],
                status_code=int(row.get("Status", 0) or 0),
                ip_address=row.get("IP", "") or None,
                user_agent=row.get("Browser", "")[:512],
                referrer=row.get("Referrer", "")[:512],
                duration_ms=float(row.get("Duration (ms)", 0) or 0),
                action_type=row.get("Action", "")[:64],
                session_key="",
                extra_meta={},
                created_at=self._parse_ts(row.get("Timestamp") or timezone.now().isoformat()),
            )
            return 1
        else:
            ErrorLog.objects.create(
                user=None,
                path=row.get("Path", "")[:512],
                method=row.get("Method", "")[:10],
                status_code=int(row.get("Status", 500) or 500),
                message=row.get("Message", "")[:2000],
                traceback=row.get("Traceback", "")[:8000] if row.get("Traceback") else "",
                ip_address=row.get("IP", "") or None,
                user_agent=row.get("Browser", "")[:512],
                referrer=row.get("Referrer", "")[:512],
                resolved=(row.get("Resolved", "").lower() in {"yes", "true", "1"}),
                created_at=self._parse_ts(row.get("Timestamp") or timezone.now().isoformat()),
            )
            return 1


class HolidayManagementView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/holiday_management.html"
    management_system_key = ManagementSystem.Keys.HOLIDAY

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["holidays"] = Holiday.objects.order_by("date")
        context["form"] = kwargs.get("form") or HolidayForm()
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "create")
        if action == "delete":
            holiday_id = request.POST.get("holiday_id")
            holiday = get_object_or_404(Holiday, pk=holiday_id)
            holiday.delete()
            messages.success(request, "Holiday removed.")
            return redirect("superadmin:holiday_management")
        form = HolidayForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Holiday added successfully.")
            return redirect("superadmin:holiday_management")
        return self.render_to_response(self.get_context_data(form=form))


class JobDeadlineUpdateView(SuperAdminAccessMixin, FormView):
    template_name = "superadmin/job_deadline_form.html"
    form_class = JobDeadlineForm
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def dispatch(self, request, *args, **kwargs):
        self.job = get_object_or_404(Job, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.job
        return kwargs

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.updated_by = self.request.user
        obj.save()
        messages.success(self.request, "Job deadlines updated.")
        return redirect("superadmin:job_detail", pk=self.job.pk)


class ManagementSystemControlView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/system_control.html"
    management_system_key = None

    def get_formset(self, data=None):
        FormSet = modelformset_factory(
            ManagementSystem, form=ManagementSystemForm, extra=0
        )
        queryset = ManagementSystem.objects.order_by("name")
        return FormSet(data=data, queryset=queryset, prefix="systems")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["formset"] = kwargs.get("formset") or self.get_formset()
        context["focus_key"] = self.request.GET.get("focus")
        return context

    def post(self, request, *args, **kwargs):
        formset = self.get_formset(data=request.POST)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Management systems updated successfully.")
            return redirect("superadmin:system_control")
        context = self.get_context_data(formset=formset)
        return self.render_to_response(context)


class CouponManagementView(SuperAdminAccessMixin, TemplateView):
    """Create and manage coupons for global users."""

    template_name = "superadmin/coupon_management.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT
    TASK_CHOICES = [
        ("summary", "Analyze / Summary"),
        ("structure", "Structure"),
        ("content", "Content"),
        ("referencing", "Referencing"),
        ("monster", "Monster"),
    ]

    def _parse_dt(self, value):
        if not value:
            return None
        try:
            dt = datetime.datetime.fromisoformat(value)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except Exception:
            return None

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "create")
        if action == "toggle":
            coupon_id = request.POST.get("coupon_id")
            coupon = Coupon.objects.filter(pk=coupon_id).first()
            if not coupon:
                messages.error(request, "Coupon not found.")
                return redirect("superadmin:coupon_management")
            coupon.is_active = not coupon.is_active
            coupon.save(update_fields=["is_active", "updated_at"])
            state = "activated" if coupon.is_active else "deactivated"
            messages.success(request, f"{coupon.code} {state}.")
            return redirect("superadmin:coupon_management")

        code = (request.POST.get("code") or "").strip()
        description = (request.POST.get("description") or "").strip()
        discount_type = request.POST.get("discount_type") or Coupon.DiscountType.FIXED
        amount_raw = request.POST.get("amount") or "0"
        max_uses = int(request.POST.get("max_uses_per_user") or 1)
        valid_from = self._parse_dt(request.POST.get("valid_from"))
        valid_to = self._parse_dt(request.POST.get("valid_to"))
        applies_to_all = request.POST.get("applies_to_all") == "on"
        task_keys = request.POST.getlist("applicable_tasks") or [t[0] for t in self.TASK_CHOICES]
        assigned_ids = request.POST.getlist("assigned_users")

        if not code:
            messages.error(request, "Code is required.")
            return redirect("superadmin:coupon_management")
        try:
            amount = Decimal(str(amount_raw))
        except Exception:
            messages.error(request, "Invalid amount.")
            return redirect("superadmin:coupon_management")
        if discount_type == Coupon.DiscountType.PERCENT and amount > 100:
            messages.error(request, "Percent discount cannot exceed 100%.")
            return redirect("superadmin:coupon_management")
        if not valid_from or not valid_to or valid_to < valid_from:
            messages.error(request, "Please provide a valid date range.")
            return redirect("superadmin:coupon_management")
        if not applies_to_all and not assigned_ids:
            messages.error(request, "Select at least one user or mark applies to all.")
            return redirect("superadmin:coupon_management")
        try:
            coupon = Coupon.objects.create(
                code=code,
                description=description,
                discount_type=discount_type,
                amount=amount,
                max_uses_per_user=max_uses,
                valid_from=valid_from,
                valid_to=valid_to,
                is_active=True,
                applies_to_all=applies_to_all,
                applicable_tasks=task_keys,
                created_by=request.user,
            )
            if not applies_to_all and assigned_ids:
                users = User.objects.filter(pk__in=assigned_ids, role=User.Role.GLOBAL)
                coupon.assigned_users.set(users)
            messages.success(request, f"Coupon {coupon.code} created.")
        except Exception as exc:
            messages.error(request, f"Could not create coupon: {exc}")
        return redirect("superadmin:coupon_management")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        coupons = list(Coupon.objects.all().order_by("-valid_to", "code"))
        global_users = User.objects.filter(role=User.Role.GLOBAL).order_by("email")
        coupons_qs = Coupon.objects.all().order_by("-valid_to", "code")
        coupon_paginator = Paginator(coupons_qs, 5)
        coupon_page_number = self.request.GET.get("coupon_page")
        coupon_page_obj = coupon_paginator.get_page(coupon_page_number)

        redemptions_qs = CouponRedemption.objects.select_related("coupon", "user").order_by("-created_at")
        redemption_paginator = Paginator(redemptions_qs, 5)
        redemption_page_number = self.request.GET.get("redemption_page")
        redemption_page_obj = redemption_paginator.get_page(redemption_page_number)

        base_query = self.request.GET.copy()
        if "coupon_page" in base_query:
            base_query.pop("coupon_page")
        if "redemption_page" in base_query:
            base_query.pop("redemption_page")
        context.update(
            coupons=list(coupon_page_obj.object_list),
            coupon_page_obj=coupon_page_obj,
            coupon_paginator=coupon_paginator,
            redemptions=list(redemption_page_obj.object_list),
            redemption_page_obj=redemption_page_obj,
            redemption_paginator=redemption_paginator,
            base_query=base_query.urlencode(),
            global_users=global_users,
            task_choices=self.TASK_CHOICES,
        )
        return context

class ManagementHubView(SuperAdminAccessMixin, TemplateView):
    """Landing page listing all management/system tools."""

    template_name = "superadmin/management_hub.html"
    management_system_key = None


class FormManagementListView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/form_management_list.html"
    management_system_key = ManagementSystem.Keys.FORM

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["forms"] = FormDefinition.objects.all().order_by("slug")
        return context

    def post(self, request, *args, **kwargs):
        form_id = request.POST.get("form_id")
        if not form_id:
            messages.error(request, "Missing form id.")
            return redirect("superadmin:form_management_list")
        form_def = get_object_or_404(FormDefinition, pk=form_id)
        form_def.is_active = not form_def.is_active
        form_def.save(update_fields=["is_active"])
        state = "activated" if form_def.is_active else "deactivated"
        messages.success(request, f"{form_def.name} {state}.")
        return redirect("superadmin:form_management_list")


class FormManagementView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/form_management.html"
    management_system_key = ManagementSystem.Keys.FORM

    def get_definition(self):
        return get_object_or_404(FormDefinition, slug=self.kwargs["slug"])

    def get_formset(self, data=None):
        definition = self.get_definition()
        FormSet = modelformset_factory(
            FormField,
            form=FormFieldForm,
            extra=1,
        )
        qs = definition.fields.order_by("order", "id")
        return FormSet(queryset=qs, data=data, prefix="fields")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["definition"] = self.get_definition()
        context["formset"] = kwargs.get("formset") or self.get_formset()
        return context

    def post(self, request, *args, **kwargs):
        formset = self.get_formset(data=request.POST)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Form updated successfully.")
            return redirect(
                "superadmin:form_management", slug=self.kwargs.get("slug")
            )
        return self.render_to_response(self.get_context_data(formset=formset))


class NavigationOrderView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/navigation_order.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def _available_roles(self):
        if not NavigationItem:
            return []
        return list(
            NavigationItem.objects.values_list("role", flat=True)
            .distinct()
            .order_by("role")
        )

    def _current_role(self):
        roles = self._available_roles()
        return (
            self.request.POST.get("role")
            or self.request.GET.get("role")
            or (roles[0] if roles else None)
        )

    def get_formset(self, data=None):
        if not NavigationItem:
            return None
        FormSet = modelformset_factory(
            NavigationItem,
            fields=["order", "is_active"],
            extra=0,
        )
        role = self._current_role()
        if not role:
            return None
        qs = NavigationItem.objects.filter(role=role).order_by("role", "order", "id")
        return FormSet(queryset=qs, data=data, prefix="nav")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["formset"] = kwargs.get("formset") or self.get_formset()
        context["roles"] = self._available_roles()
        context["selected_role"] = self._current_role()
        return context

    def post(self, request, *args, **kwargs):
        formset = self.get_formset(data=request.POST)
        if formset is None:
            messages.error(request, "Navigation management is unavailable.")
            return redirect("superadmin:dashboard")
        if formset.is_valid():
            formset.save()
            messages.success(request, "Navigation order updated.")
            return redirect(f"{reverse('superadmin:navigation_order')}?role={self._current_role()}")
        return self.render_to_response(self.get_context_data(formset=formset))


class FloorSignupRequestListView(SuperAdminAccessMixin, TemplateView):
    template_name = "superadmin/floor_signup_requests.html"
    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        req_id = request.POST.get("req_id")
        req = FloorSignupRequest.objects.filter(pk=req_id).first()
        if not req:
            messages.error(request, "Request not found.")
            return redirect("superadmin:floor_signup_requests")
        if action == "approve":
            if req.status == FloorSignupRequest.Status.APPROVED:
                messages.info(request, "Already approved.")
                return redirect("superadmin:floor_signup_requests")
            # Do NOT reuse existing emails; floor accounts must use a unique email
            if User.objects.filter(email__iexact=req.email).exists():
                messages.error(
                    request,
                    "Email already exists on another account. Please ask the requester to submit with a different email.",
                )
                return redirect("superadmin:floor_signup_requests")
            username, password = req.generate_credentials()
            # if somehow username already exists, regenerate until unique
            attempts = 0
            while User.objects.filter(floor_username=username).exists() and attempts < 5:
                username, password = req.generate_credentials()
                attempts += 1
            try:
                user = User.objects.create_user(
                    email=req.email,
                    password=password,
                    first_name=req.first_name,
                    last_name=req.last_name,
                    role=User.Role.FLOOR,
                    whatsapp_country_code=req.whatsapp_country_code,
                    whatsapp_number=req.whatsapp_number,
                    last_qualification=req.last_qualification,
                    is_account_approved=True,
                    is_active=True,
                    floor_username=username,
                )
                req.generated_username = username
                req.generated_password = password
                req.status = FloorSignupRequest.Status.APPROVED
                req.decided_by = request.user
                req.decided_at = timezone.now()
                req.save()
                messages.success(request, f"Approved and created floor user {username}.")
            except Exception:
                messages.error(request, "Could not create floor user. Please ensure email/username are unique.")
        elif action == "reject":
            req.status = FloorSignupRequest.Status.REJECTED
            req.decided_by = request.user
            req.decided_at = timezone.now()
            req.decision_notes = request.POST.get("notes", "")
            req.save(update_fields=["status", "decided_by", "decided_at", "decision_notes"])
            messages.info(request, "Request rejected.")
        return redirect("superadmin:floor_signup_requests")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pending_qs = FloorSignupRequest.objects.filter(status=FloorSignupRequest.Status.PENDING).order_by("created_at")
        approved_qs = FloorSignupRequest.objects.filter(status=FloorSignupRequest.Status.APPROVED).order_by("-decided_at")
        rejected_qs = FloorSignupRequest.objects.filter(status=FloorSignupRequest.Status.REJECTED).order_by("-decided_at")

        def build_rows(qs, kind):
            rows = []
            if kind == "pending":
                for req in qs:
                    actions = (
                        f'<form method="post" class="d-inline me-1">{self._csrf()}'
                        f'<input type="hidden" name="req_id" value="{req.id}">'
                        f'<input type="hidden" name="action" value="approve">'
                        f'<button class="btn btn-sm btn-success" type="submit">Approve</button></form>'
                        f'<form method="post" class="d-inline">{self._csrf()}'
                        f'<input type="hidden" name="req_id" value="{req.id}">'
                        f'<input type="hidden" name="action" value="reject">'
                        f'<input type="hidden" name="notes" value="Rejected by admin">'
                        f'<button class="btn btn-sm btn-outline-danger" type="submit">Reject</button></form>'
                    )
                    rows.append(
                        [
                            f"{req.first_name} {req.last_name}",
                            req.email,
                            req.last_qualification,
                            req.created_at.strftime("%d %b %Y, %I:%M %p"),
                            actions,
                        ]
                    )
            elif kind == "approved":
                for req in qs:
                    rows.append(
                        [
                            f"{req.first_name} {req.last_name}",
                            req.email,
                            f"<code>{req.generated_username}</code>",
                            f"<code>{req.generated_password}</code>",
                            req.decided_at.strftime("%d %b %Y, %I:%M %p") if req.decided_at else "-",
                            req.decided_by.get_full_name() if req.decided_by else "-",
                        ]
                    )
            else:  # rejected
                for req in qs:
                    rows.append(
                        [
                            f"{req.first_name} {req.last_name}",
                            req.email,
                            req.decision_notes or "-",
                            req.decided_at.strftime("%d %b %Y, %I:%M %p") if req.decided_at else "-",
                        ]
                    )
            return rows

        from django.core.paginator import Paginator
        pending_pag = Paginator(pending_qs, 5)
        approved_pag = Paginator(approved_qs, 5)
        rejected_pag = Paginator(rejected_qs, 5)

        pending_page = pending_pag.get_page(self.request.GET.get("pending_page"))
        approved_page = approved_pag.get_page(self.request.GET.get("approved_page"))
        rejected_page = rejected_pag.get_page(self.request.GET.get("rejected_page"))

        context.update(
            pending_headers=["Name", "Email", "Qualification", "Submitted", "Actions"],
            pending_rows=build_rows(pending_page.object_list, "pending"),
            pending_page=pending_page,
            approved_headers=["Name", "Email", "Username", "Password", "Decided", "By"],
            approved_rows=build_rows(approved_page.object_list, "approved"),
            approved_page=approved_page,
            rejected_headers=["Name", "Email", "Notes", "Decided"],
            rejected_rows=build_rows(rejected_page.object_list, "rejected"),
            rejected_page=rejected_page,
        )
        return context

    def _csrf(self):
        # Render a CSRF token input; used only for string-building here
        from django.middleware.csrf import get_token

        token = get_token(self.request)
        return f'<input type="hidden" name="csrfmiddlewaretoken" value="{token}">'
