"""Marketing role views."""

import datetime
import io
import re
from collections import defaultdict
from decimal import Decimal
from types import SimpleNamespace
import math

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, TemplateView

from accounts.forms import GlobalProfileEditForm
from accounts.models import User
from common.mixins import ManagementSystemGateMixin
from common.models import ManagementSystem, Notice, Coupon, CouponRedemption
from common.utils import format_currency, localize_deadline, to_decimal
from jobs.choices import ContentSectionType, ContentStatus
from jobs.forms import JobDeleteForm
from jobs.models import Job, Holiday, JobContentSectionHistory, JobContentSection
from jobs.services import (
    get_job_cards_for_user,
    _generate_with_gemini,
    SUMMARY_PROMPT,
)
from accounts.models import GemsAccount, GemTransaction
from marketing.models import AnalyzeHistory, StructureHistory, ContentHistory, MonsterHistory, ReferencingHistory
from marketing.gem_rates import get_gem_rates
from accounts.views import ensure_gems_account
from superadmin.forms import JobSectionActionForm
from jobs.models import JobContentSection
from jobs.services import (
    generate_job_summary,
    generate_structure_from_summary,
    generate_content_from_structure,
    generate_references_from_content,
    generate_final_document_with_citations,
    sync_job_approval,
)
from pagebuilder.utils import build_page

from .forms import JobDropForm
from common.models import GemCostRule

# Default gems costs (applied unless overridden by GemCostRule)
SECTION_GEM_COST_DEFAULTS = {
    ContentSectionType.SUMMARY: Decimal("2"),
    ContentSectionType.STRUCTURE: Decimal("2"),
    ContentSectionType.CONTENT: Decimal("4"),
    ContentSectionType.REFERENCING: Decimal("1"),
    ContentSectionType.PLAG_REPORT: Decimal("3"),
    ContentSectionType.AI_REPORT: Decimal("3"),
    ContentSectionType.FULL_CONTENT: Decimal("5"),
}
MONSTER_GEM_COST_DEFAULT = Decimal("10")


def get_section_cost(section_key):
    """Fetch a gem cost override; fallback to defaults."""
    try:
        rule = GemCostRule.objects.filter(key=section_key).first()
        if rule:
            return Decimal(str(rule.cost))
    except Exception:
        pass
    return SECTION_GEM_COST_DEFAULTS.get(section_key, Decimal("0"))


def get_monster_cost():
    try:
        rule = GemCostRule.objects.filter(key=GemCostRule.Keys.MONSTER).first()
        if rule:
            return Decimal(str(rule.cost))
    except Exception:
        pass
    return MONSTER_GEM_COST_DEFAULT


def _coupon_applicable(user, task_key, cost):
    """Return (coupon, discount) best applicable for a user/task."""
    now = timezone.now()
    coupons = list(Coupon.objects.all())
    redemptions = list(CouponRedemption.objects.all())
    user_id = getattr(user, "pk", None)
    applicable = []
    for c in coupons:
        try:
            if not c.is_active:
                continue
            if c.valid_from and now < c.valid_from:
                continue
            if c.valid_to and now > c.valid_to:
                continue
            if not c.applies_to_all and user_id:
                if not c.assigned_users.filter(pk=user_id).exists():
                    continue
            tasks = c.applicable_tasks or []
            if tasks and task_key not in tasks:
                continue
            used = len([r for r in redemptions if r.coupon_id == c.id and r.user_id == user_id])
            if used >= c.max_uses_per_user:
                continue
            applicable.append(c)
        except Exception:
            continue
    best_coupon = None
    best_discount = Decimal("0")
    for c in applicable:
        if c.discount_type == c.DiscountType.FIXED:
            discount = min(Decimal(str(c.amount)), cost)
        else:
            discount = (cost * Decimal(str(c.amount)) / Decimal("100")).quantize(Decimal("0.01"))
            discount = min(discount, cost)
        if discount > best_discount:
            best_discount = discount
            best_coupon = c
    return best_coupon, best_discount


def _apply_coupon(user, task_key, cost, code=None):
    """Apply a specific coupon code; if none provided, no discount.

    Returns: (coupon, net_cost, discount, status, warning)
    status: "ok", "not_applicable"
    warning: True when coupon value exceeds cost (informational only)
    """
    if not code:
        return None, cost, Decimal("0"), "ok", False
    try:
        coupon = Coupon.objects.filter(code__iexact=code.strip()).first()
    except Exception:
        coupon = None
    if not coupon:
        return None, cost, Decimal("0"), "not_applicable", False
    # verify applicability
    now = timezone.now()
    try:
        if not coupon.is_active:
            return None, cost, Decimal("0"), "not_applicable", False
        if coupon.valid_from and now < coupon.valid_from:
            return None, cost, Decimal("0"), "not_applicable", False
        if coupon.valid_to and now > coupon.valid_to:
            return None, cost, Decimal("0"), "not_applicable", False
        if not coupon.applies_to_all and not coupon.assigned_users.filter(pk=getattr(user, "pk", None)).exists():
            return None, cost, Decimal("0"), "not_applicable", False
        tasks = coupon.applicable_tasks or []
        if tasks and task_key not in tasks:
            return None, cost, Decimal("0"), "not_applicable", False
        used = CouponRedemption.objects.filter(coupon=coupon, user=user).count()
        if used >= coupon.max_uses_per_user:
            return None, cost, Decimal("0"), "not_applicable", False
        if coupon.discount_type == coupon.DiscountType.FIXED:
            discount = min(Decimal(str(coupon.amount)), cost)
        else:
            discount = (cost * Decimal(str(coupon.amount)) / Decimal("100")).quantize(Decimal("0.01"))
            discount = min(discount, cost)
        net = max(Decimal("0"), cost - discount)
        warning = discount > cost
        return coupon, net, discount, "ok", warning
    except Exception:
        return None, cost, Decimal("0"), "not_applicable", False
ANALYZE_HISTORY_SESSION_KEY = "analyze_history"
STRUCTURE_HISTORY_SESSION_KEY = "structure_history"
CONTENT_HISTORY_SESSION_KEY = "content_history"


def _extract_text_from_uploads(files, max_files=10):
    """Best-effort extraction from uploaded files for ad-hoc analysis."""
    texts = []
    count = 0
    for f in files:
        if count >= max_files:
            break
        count += 1
        name = (getattr(f, "name", "") or "").lower()
        try:
            data = f.read()
            f.seek(0)
        except Exception:
            continue
        # simple decoders by extension
        try:
            if name.endswith(".pdf"):
                from PyPDF2 import PdfReader

                reader = PdfReader(io.BytesIO(data))
                parts = [page.extract_text() or "" for page in reader.pages]
                texts.append("\n".join(parts).strip())
                continue
            if name.endswith(".docx"):
                import docx

                doc = docx.Document(io.BytesIO(data))
                texts.append("\n".join(p.text for p in doc.paragraphs))
                continue
            if name.endswith(".csv"):
                import pandas as pd

                df = pd.read_csv(io.BytesIO(data))
                texts.append(df.to_csv(index=False))
                continue
            if name.endswith((".xlsx", ".xls")):
                import pandas as pd

                df = pd.read_excel(io.BytesIO(data))
                texts.append(df.to_csv(index=False))
                continue
            if name.endswith(".txt"):
                texts.append(data.decode("utf-8", errors="ignore"))
                continue
        except Exception:
            # fall back to raw decode below
            pass
        try:
            texts.append(data.decode("utf-8", errors="ignore"))
        except Exception:
            continue
    return "\n\n".join(t for t in texts if t).strip()

class DateRangeChartMixin:
    """Shared helpers for date range and chart data."""

    def _get_date_range(self):
        today = datetime.date.today()
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
        job_amounts = {d: to_decimal(0) for d in labels}
        for job in jobs:
            day = job.created_at.date()
            if day in job_counts:
                job_counts[day] += 1
                job_amounts[day] += to_decimal(job.amount_inr)

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


class MarketingAccessMixin(
    ManagementSystemGateMixin, LoginRequiredMixin, UserPassesTestMixin
):
    """Restrict views to marketing accounts only."""

    management_system_key = ManagementSystem.Keys.WEBSITE_CONTENT

    def test_func(self):
        return self.request.user.role in {User.Role.MARKETING, User.Role.GLOBAL}

    def handle_no_permission(self):
        return redirect("common:welcome")


class MarketingWelcomeView(DateRangeChartMixin, MarketingAccessMixin, TemplateView):
    template_name = "marketing/welcome.html"

    def dispatch(self, request, *args, **kwargs):
        user = getattr(request, "user", None)
        if (
            user
            and getattr(user, "is_authenticated", False)
            and getattr(user, "role", None) == User.Role.GLOBAL
        ):
            return redirect("marketing:global_home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cards"] = get_job_cards_for_user(self.request.user)
        start, end = self._get_date_range()
        start_dt, end_dt = self._get_datetime_bounds(start, end)
        jobs = Job.objects.filter(
            created_by=self.request.user,
            is_deleted__in=[False],
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        )
        context["chart_data"] = self._build_chart_data(jobs, start, end)
        context["start_date"] = start
        context["end_date"] = end
        return context


class GlobalAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restrict to global users only."""

    def test_func(self):
        return self.request.user.role == User.Role.GLOBAL

    def handle_no_permission(self):
        return redirect("common:welcome")


class GlobalDashboardView(GlobalAccessMixin, DateRangeChartMixin, TemplateView):
    """Global home: profile snapshot, gems balance, and generation insights."""

    template_name = "marketing/global_dashboard.html"

    def _get_stats(self, user):
        jobs = Job.objects.filter(created_by=user, is_deleted=False)
        total_jobs = jobs.count()
        sections_generated = (
            JobContentSection.objects.filter(job__created_by=user)
            .exclude(content__isnull=True)
            .exclude(content__exact="")
            .count()
        )
        recent_window = timezone.now() - datetime.timedelta(days=30)
        # count monster runs in last 30 days
        monster_recent = MonsterHistory.objects.filter(
            user=user, created_at__gte=recent_window
        ).count()
        return {
            "total_jobs": total_jobs,
            "sections_generated": sections_generated,
            "jobs_recent": monster_recent,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        try:
            user.refresh_from_db(fields=["first_name", "last_name", "profile_picture"])
        except (User.DoesNotExist, NotImplementedError):
            user = self.request.user
        context["dashboard_user"] = user
        context["profile_avatar_url"] = (
            user.profile_picture.url if user.profile_picture else None
        )
        account = ensure_gems_account(user, "Welcome bonus (Global user)")
        context["gems_balance"] = account.balance

        stats = self._get_stats(user)
        context["stats"] = stats

        summary_reason_labels = {"Analyze Document (Summary)", "Job Summary generation"}
        structure_reason_labels = {"Global Structure generation"}
        gems_spent_total = Decimal("0")
        summary_generated = 0
        structure_generated = 0
        for tx in GemTransaction.objects.filter(user=user):
            amount = to_decimal(tx.amount)
            if amount < 0:
                gems_spent_total += abs(amount)
            if tx.reason in summary_reason_labels:
                summary_generated += 1
            if tx.reason in structure_reason_labels:
                structure_generated += 1

        context["cards"] = []
        context["gems_spent_total"] = gems_spent_total
        context["recent_jobs"] = stats.get("jobs_recent", 0)
        context["last_login_display"] = (
            user.last_login.strftime("%d %b %Y, %I:%M %p")
            if user.last_login
            else "No activity recorded"
        )
        gem_rates = get_gem_rates()
        rows = []
        try:
            rates = gem_rates.get("rates", {})
            prices = gem_rates.get("prices", {})
            for curr in gem_rates.get("currencies", []):
                rows.append((curr, rates.get(curr), prices.get(curr)))
        except Exception:
            rows = []
        context["gem_rates"] = gem_rates
        context["gem_rate_rows"] = rows

        context["profile_details"] = [
            ("Role", user.get_role_display()),
            ("Email", user.email),
            ("Employee ID", user.employee_id or "Pending"),
            ("Floor Username", user.floor_username or "Not assigned"),
            ("Joined", user.date_joined.strftime("%d %b %Y")),
            (
                "Last Login",
                user.last_login.strftime("%d %b %Y, %I:%M %p")
                if user.last_login
                else "—",
            ),
        ]

        sections_qs = (
            JobContentSection.objects.filter(job__created_by=user)
            .exclude(content__isnull=True)
            .exclude(content__exact="")
        )
        sections = list(sections_qs)
        db_summary_generated = sum(
            1 for section in sections if section.section_type == ContentSectionType.SUMMARY
        )
        db_structure_generated = sum(
            1 for section in sections if section.section_type == ContentSectionType.STRUCTURE
        )
        content_words_total = sum(
            len((section.content or "").split())
            for section in sections
            if section.section_type == ContentSectionType.CONTENT
        )
        summary_generated = max(summary_generated, db_summary_generated)
        structure_generated = max(structure_generated, db_structure_generated)
        analyze_history = AnalyzeHistory.objects.filter(user=user)
        structure_history = StructureHistory.objects.filter(user=user)
        content_history_qs = ContentHistory.objects.filter(user=user)
        summary_generated = max(summary_generated, analyze_history.count())
        structure_generated = max(structure_generated, structure_history.count())

        content_words_from_history = (
            content_history_qs.aggregate(total=models.Sum("word_count")).get("total") or 0
        )
        # Fallback: if any history missing word_count, approximate from text length
        missing_words = sum(
            len((item.result or "").split())
            for item in content_history_qs
            if item.word_count is None
        )
        content_words_total += content_words_from_history + missing_words
        context["summary_generated_total"] = summary_generated
        context["structure_generated_total"] = structure_generated
        context["content_words_total"] = content_words_total
        base_month = timezone.now().date().replace(day=1)
        month_keys = []
        year = base_month.year
        month = base_month.month
        for _ in range(6):
            month_keys.append(datetime.date(year, month, 1))
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        month_keys.reverse()
        word_bucket = defaultdict(int)
        generation_bucket = defaultdict(int)
        for section in sections:
            dt = section.updated_at or section.created_at or timezone.now()
            key = datetime.date(dt.year, dt.month, 1)
            if key < month_keys[0]:
                continue
            word_bucket[key] += len((section.content or "").split())
            generation_bucket[key] += 1
        context["word_count_labels"] = [key.strftime("%b %Y") for key in month_keys]
        context["word_count_values"] = [word_bucket.get(key, 0) for key in month_keys]
        context["generation_labels"] = context["word_count_labels"]
        context["generation_values"] = [generation_bucket.get(key, 0) for key in month_keys]
        context["recent_window_label"] = "Last 6 months"
        return context


class GlobalGemsHistoryView(GlobalAccessMixin, TemplateView):
    """Dedicated gems history listing for global users."""

    template_name = "marketing/global_history.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        account = ensure_gems_account(user, "Welcome bonus (Global user)")
        context["gems_balance"] = account.balance
        transactions_qs = (
            GemTransaction.objects.filter(user=user).order_by("-created_at", "-id")
        )
        transactions = list(transactions_qs)
        for tx in transactions:
            amount = to_decimal(tx.amount)
            tx.display_amount = amount
            tx.is_credit = amount >= 0
            tx.is_debit = amount < 0
            if tx.created_by:
                if (
                    tx.is_credit
                    and tx.created_by.role
                    in {User.Role.SUPER_ADMIN, User.Role.CO_SUPER_ADMIN}
                ):
                    processor_label = "Passed by Team Assignment Monster"
                else:
                    processor_name = (
                        tx.created_by.get_full_name() or tx.created_by.email or "User"
                    )
                    processor_label = f"Processed by {processor_name}"
            else:
                processor_label = (
                    "Passed by Team Assignment Monster"
                    if tx.is_credit
                    else "Triggered by user action"
                )
            tx.processor_label = processor_label
        paginator = Paginator(transactions, 5)
        gems_page_number = self.request.GET.get("gems_page") or 1
        gems_page = paginator.get_page(gems_page_number)
        context["recent_transactions"] = gems_page.object_list
        context["gems_tx_page"] = gems_page
        base_query = self.request.GET.copy()
        if "gems_page" in base_query:
            base_query.pop("gems_page")
        context["gems_base_query"] = base_query.urlencode()
        return context


class GlobalNoticeListView(GlobalAccessMixin, TemplateView):
    """List active notices for global users."""

    template_name = "marketing/global_notices.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["notices"] = list(Notice.active_for_user(self.request.user))
        except Exception:
            context["notices"] = []
        return context


class GlobalCouponsView(GlobalAccessMixin, TemplateView):
    """List available coupons for global users."""

    template_name = "marketing/global_coupons.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        available = []
        now = timezone.now()
        coupons = list(Coupon.objects.all())
        for c in coupons:
            try:
                if not c.is_active:
                    continue
                if not c.is_valid_for_user(user):
                    continue
                if c.valid_from and now < c.valid_from:
                    continue
                if c.valid_to and now > c.valid_to:
                    continue
                used = CouponRedemption.objects.filter(coupon=c, user=user).count()
                if used >= c.max_uses_per_user:
                    continue
                available.append(
                    {
                        "code": c.code,
                        "description": c.description,
                        "tasks": c.applicable_tasks or ["summary", "structure", "content", "monster"],
                        "valid_from": c.valid_from,
                        "valid_to": c.valid_to,
                        "uses_left": max(0, c.max_uses_per_user - used),
                    }
                )
            except Exception:
                continue
        context["coupons"] = available
        return context


class GlobalProfileEditView(GlobalAccessMixin, FormView):
    """Simple profile editor for global users (names + avatar)."""

    template_name = "marketing/global_profile_edit.html"
    form_class = GlobalProfileEditForm
    success_url = reverse_lazy("marketing:global_home")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Profile updated successfully.")
        return super().form_valid(form)


class GlobalAnalyzeView(GlobalAccessMixin, TemplateView):
    """Landing page for document analysis / AI removal quick links (UI only)."""

    template_name = "marketing/global_analyze.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = ensure_gems_account(self.request.user, "Welcome bonus")
        context["gems_balance"] = account.balance
        context["summary_cost"] = get_section_cost(ContentSectionType.SUMMARY)
        context.setdefault("result", None)
        context.setdefault("deducted", None)
        context.setdefault("new_balance", account.balance)
        qs = AnalyzeHistory.objects.filter(user=self.request.user).order_by("-created_at", "-id")
        page = int(self.request.GET.get("hist_page", "1") or 1)
        paginator = Paginator(qs, 3)
        page_obj = paginator.get_page(page)
        total_pages = paginator.num_pages or 1
        window = 5
        start_page = max(1, page_obj.number - window // 2)
        end_page = min(total_pages, start_page + window - 1)
        start_page = max(1, end_page - window + 1)
        context["history_page"] = list(page_obj.object_list)
        context["history_page_number"] = page_obj.number
        context["history_total_pages"] = total_pages
        context["history_page_numbers"] = list(range(start_page, end_page + 1))
        return context

    # Allow form submissions without a 405. We simply re-render with the same context.
    def post(self, request, *args, **kwargs):
        instruction = (request.POST.get("instruction") or "").strip()
        files = request.FILES.getlist("attachments")
        if not instruction:
            messages.error(request, "Instruction is required.")
            return self.render_to_response(self.get_context_data(**kwargs))

        if len(files) > 10:
            files = files[:10]
            messages.warning(request, "Only the first 10 attachments were used.")

        # Build combined text for summary generation
        attachment_text = _extract_text_from_uploads(files)
        combined = instruction
        if attachment_text:
            combined += (
                "\n\nAttached file text (best-effort extraction):\n" + attachment_text
            )

        cost = get_section_cost(ContentSectionType.SUMMARY)
        account = ensure_gems_account(request.user, "Welcome bonus")
        coupon, net_cost, discount, status, warning = _apply_coupon(
            request.user, ContentSectionType.SUMMARY, cost, code=request.POST.get("coupon_code")
        )
        if status != "ok":
            messages.error(request, "Coupon not applicable to this task.")
            return self.render_to_response(self.get_context_data(**kwargs))
        if account.balance < net_cost:
            messages.error(
                request,
                f"Not enough gems to analyze (requires {net_cost}, you have {account.balance}).",
            )
            return self.render_to_response(self.get_context_data(**kwargs))

        prompt = f"{SUMMARY_PROMPT}\n\nUSER INPUT:\n{combined}"
        summary = _generate_with_gemini(prompt, fallback=instruction)

        # Deduct gems on success
        account.balance -= net_cost
        account.save(update_fields=["balance"])
        GemTransaction.objects.create(
            user=request.user,
            amount=-net_cost,
            reason="Analyze Document (Summary)",
            created_by=request.user,
        )
        if coupon and discount > 0:
            CouponRedemption.objects.create(
                coupon=coupon,
                user=request.user,
                task_type=ContentSectionType.SUMMARY,
                gems_discounted=discount,
            )
        AnalyzeHistory.objects.create(
            user=request.user,
            instruction=instruction,
            result=summary,
        )
        messages.success(
            request,
            f"Summary generated. {net_cost} gems deducted. Remaining balance: {account.balance}." + (f" Coupon {coupon.code} applied (-{discount} gems)." if coupon and discount else ""),
        )
        ctx = self.get_context_data(**kwargs)
        ctx.update(
            {
                "result": summary,
                "deducted": net_cost,
                "new_balance": account.balance,
            }
        )
        return self.render_to_response(ctx)


def _get_global_store(request):
    store = request.session.get("global_step_store", {})
    request.session["global_step_store"] = store
    return store


def _save_global_store(request, store):
    request.session["global_step_store"] = store
    request.session.modified = True


class GlobalStepBase(GlobalAccessMixin, TemplateView):
    step_key = ""
    template_name = "marketing/global_step.html"
    title = ""
    next_url = None
    cost_func = lambda self, data: get_section_cost(self.step_key)

    def _charge(self, user, amount, reason):
        if amount <= 0:
            return True
        account = ensure_gems_account(user, "Welcome bonus")
        if account.balance < amount:
            return False
        account.balance -= amount
        account.save(update_fields=["balance"])
        GemTransaction.objects.create(user=user, amount=-amount, reason=reason, created_by=user)
        return True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        store = _get_global_store(self.request)
        account = ensure_gems_account(self.request.user, "Welcome bonus")
        context.update(
            {
                "title": self.title,
                "step_key": self.step_key,
                "output": store.get(self.step_key, ""),
                "store": store,
                "gems_balance": account.balance,
                "next_url": self.next_url,
                "cost": self.cost_func({}),
                "cost_note": "",
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        store = _get_global_store(request)
        account = ensure_gems_account(request.user, "Welcome bonus")
        output = ""
        # basic inputs
        instruction = request.POST.get("instruction", "").strip()

        # compute cost
        data = {"instruction": instruction}
        cost = self.cost_func(data)
        if cost > 0 and not self._charge(request.user, cost, f"{self.title} generation"):
            messages.error(request, "Not enough gems for this generation.")
            return redirect(request.path)

        # fake generation (stub) — replace with real call if available
        if self.step_key == ContentSectionType.CONTENT:
            output = f"Generated Content from breakdown:\n{instruction or 'N/A'}"
        elif self.step_key == ContentSectionType.STRUCTURE:
            output = f"Generated Structure based on summary:\n{instruction or 'N/A'}"
        elif self.step_key == ContentSectionType.SUMMARY:
            output = f"Generated Summary:\n{instruction}"
        elif self.step_key == ContentSectionType.REFERENCING:
            output = f"Generated References for content:\n{instruction or 'N/A'}"
        elif self.step_key == ContentSectionType.PLAG_REPORT:
            output = "Plagiarism report generated."
        elif self.step_key == ContentSectionType.AI_REPORT:
            output = "AI report generated."
        elif self.step_key == ContentSectionType.FULL_CONTENT:
            output = f"Final content with citations based on content:\n{instruction or 'N/A'}"
        else:
            output = "Generated output."

        store[self.step_key] = output
        _save_global_store(request, store)
        messages.success(request, f"{self.title} generated.")
        return redirect(request.path)


class GlobalSummaryView(GlobalStepBase):
    step_key = ContentSectionType.SUMMARY
    title = "Job Summary"
    next_url = reverse_lazy("marketing:global_structure")


class GlobalStructureView(GlobalAccessMixin, TemplateView):
    template_name = "marketing/global_structure.html"

    def _paginate_history(self):
        qs = StructureHistory.objects.filter(user=self.request.user).order_by("-created_at", "-id")
        page = int(self.request.GET.get("hist_page", "1") or 1)
        page_size = 3
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)
        total_pages = paginator.num_pages or 1
        window = 5
        start_page = max(1, page_obj.number - window // 2)
        end_page = min(total_pages, start_page + window - 1)
        start_page = max(1, end_page - window + 1)
        return {
            "history_page": list(page_obj.object_list),
            "history_page_number": page_obj.number,
            "history_total_pages": total_pages,
            "history_page_numbers": list(range(start_page, end_page + 1)),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = ensure_gems_account(self.request.user, "Welcome bonus")
        cost = get_section_cost(ContentSectionType.STRUCTURE)
        context.update(
            {
                "gems_balance": account.balance,
                "structure_cost": cost,
                "result": None,
                "deducted": None,
                "new_balance": account.balance,
            }
        )
        context.update(self._paginate_history())
        return context

    def post(self, request, *args, **kwargs):
        summary_text = (request.POST.get("instruction") or "").strip()
        if not summary_text:
            messages.error(request, "Summary text is required.")
            return self.render_to_response(self.get_context_data(**kwargs))

        prompt_input = summary_text

        cost = get_section_cost(ContentSectionType.STRUCTURE)
        account = ensure_gems_account(request.user, "Welcome bonus")
        coupon, net_cost, discount, status, warning = _apply_coupon(
            request.user, ContentSectionType.STRUCTURE, cost, code=request.POST.get("coupon_code")
        )
        if status != "ok":
            messages.error(request, "Coupon not applicable to this task.")
            return self.render_to_response(self.get_context_data(**kwargs))
        if account.balance < net_cost:
            messages.error(
                request, f"Not enough gems to generate structure (needs {net_cost})."
            )
            return self.render_to_response(self.get_context_data(**kwargs))

        try:
            structure = generate_structure_from_summary(prompt_input)
        except Exception:
            structure = _generate_with_gemini(
                f"Generate a full academic structure with word allocation based on this summary:\n{prompt_input}",
                fallback="Structure could not be generated due to an error.",
            )

        account.balance -= net_cost
        account.save(update_fields=["balance"])
        GemTransaction.objects.create(
            user=request.user,
            amount=-net_cost,
            reason="Global Structure generation",
            created_by=request.user,
        )
        if coupon and discount > 0:
            CouponRedemption.objects.create(
                coupon=coupon,
                user=request.user,
                task_type=ContentSectionType.STRUCTURE,
                gems_discounted=discount,
            )

        StructureHistory.objects.create(
            user=request.user,
            summary=summary_text,
            result=structure,
        )
        messages.success(
            request,
            f"Structure generated. {net_cost} gems deducted. Remaining balance: {account.balance}."
            + (f" Coupon {coupon.code} applied (-{discount} gems)." if coupon and discount else ""),
        )
        ctx = self.get_context_data(**kwargs)
        ctx.update(
            {
                "result": structure,
                "deducted": net_cost,
                "new_balance": account.balance,
            }
        )
        return self.render_to_response(ctx)


class GlobalContentView(GlobalStepBase):
    step_key = ContentSectionType.CONTENT
    title = "Content"
    next_url = reverse_lazy("marketing:global_referencing")

    @staticmethod
    def _extract_word_target(structure_text):
        if not structure_text:
            return 0
        pattern_context = re.compile(r'(\d{2,5})\s*(?:words?|wds?)', re.IGNORECASE)
        matches = [int(m) for m in pattern_context.findall(structure_text)]
        if matches:
            return sum(matches)
        trailing_pattern = re.compile(r'words?\s*(?:[:\-]|is)?\s*(\d{2,5})', re.IGNORECASE)
        matches = [int(m) for m in trailing_pattern.findall(structure_text)]
        return sum(matches)

    def _paginate_history(self):
        qs = ContentHistory.objects.filter(user=self.request.user).order_by("-created_at", "-id")
        page = int(self.request.GET.get("hist_page", "1") or 1)
        page_size = 3
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)
        total_pages = paginator.num_pages or 1
        window = 5
        start_page = max(1, page_obj.number - window // 2)
        end_page = min(total_pages, start_page + window - 1)
        start_page = max(1, end_page - window + 1)
        return {
            "history_page": list(page_obj.object_list),
            "history_page_number": page_obj.number,
            "history_total_pages": total_pages,
            "history_page_numbers": list(range(start_page, end_page + 1)),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cost_per_block = get_section_cost(ContentSectionType.CONTENT)
        context["cost_note"] = f"{cost_per_block} gem(s) per 200 words generated from your breakdown."
        context["content_history_enabled"] = True
        flash_result = self.request.session.pop("content_flash_result", None)
        flash_deducted = self.request.session.pop("content_flash_deducted", None)
        flash_balance = self.request.session.pop("content_flash_balance", None)
        context["result"] = flash_result
        context["deducted"] = flash_deducted
        context["new_balance"] = flash_balance
        context.update(self._paginate_history())
        return context

    def cost_func(self, data):
        structure_text = data.get("structure") or ""
        target = self._extract_word_target(structure_text)
        blocks = math.ceil(target / 200) if target else 1
        cost_per_block = get_section_cost(ContentSectionType.CONTENT) or Decimal("1")
        return Decimal(blocks or 1) * cost_per_block

    def post(self, request, *args, **kwargs):
        structure_text = (request.POST.get("instruction") or "").strip()

        if not structure_text:
            messages.error(
                request,
                "Structure content is required. Paste the structure output or provide detailed headings.",
            )
            return self.render_to_response(self.get_context_data(**kwargs))

        combined_structure = structure_text
        target_words = self._extract_word_target(structure_text)

        try:
            content = generate_content_from_structure(combined_structure)
        except Exception:
            fallback_prompt = (
                "Transform the following structure into full academic content with the"
                " same headings and minimum word counts per section:\n"
            )
            content = _generate_with_gemini(
                fallback_prompt + combined_structure,
                "Content could not be generated due to an error.",
            )

        generated_words = len((content or "").split())
        cost = Decimal(math.ceil(generated_words / 200)) if generated_words else Decimal("0")
        coupon, net_cost, discount, status, warning = _apply_coupon(
            request.user, ContentSectionType.CONTENT, cost, code=request.POST.get("coupon_code")
        )
        if status != "ok":
            messages.error(request, "Coupon not applicable to this task.")
            return self.render_to_response(self.get_context_data(**kwargs))
        account = ensure_gems_account(request.user, "Welcome bonus")
        if net_cost > account.balance:
            messages.error(
                request, f"Not enough gems to generate content (needs {net_cost}, you have {account.balance})."
            )
            return self.render_to_response(self.get_context_data(**kwargs))

        if net_cost > 0:
            account.balance -= net_cost
        account.save(update_fields=["balance"])
        if net_cost > 0:
            GemTransaction.objects.create(
                user=request.user,
                amount=-net_cost,
                reason="Global Content generation",
                created_by=request.user,
            )
        if coupon and discount > 0:
            CouponRedemption.objects.create(
                coupon=coupon,
                user=request.user,
                task_type=ContentSectionType.CONTENT,
                gems_discounted=discount,
            )

        store = _get_global_store(request)
        timestamp = timezone.localtime(timezone.now()).strftime("%d %b %Y, %I:%M %p")
        store["content_structure_input"] = combined_structure
        store["content_word_target"] = generated_words
        store["content_generated_at"] = timestamp
        store[self.step_key] = content
        _save_global_store(request, store)
        ContentHistory.objects.create(
            user=request.user,
            structure=combined_structure,
            result=content,
            word_count=generated_words,
        )

        messages.success(
            request,
            f"Content generated ({generated_words} words). {net_cost} gems deducted. Remaining balance: {account.balance}."
            + (f" Coupon {coupon.code} applied (-{discount} gems)." if coupon and discount else ""),
        )
        request.session["content_flash_result"] = content
        request.session["content_flash_deducted"] = str(net_cost)
        request.session["content_flash_balance"] = str(account.balance)
        request.session.modified = True
        return redirect(request.path)


class GlobalReferencingView(GlobalStepBase):
    step_key = ContentSectionType.REFERENCING
    title = "Referencing"
    next_url = reverse_lazy("marketing:global_plag")

    def _paginate_history(self):
        cutoff = timezone.now() - datetime.timedelta(days=30)
        ReferencingHistory.objects.filter(user=self.request.user, created_at__lt=cutoff).delete()
        qs = ReferencingHistory.objects.filter(user=self.request.user, created_at__gte=cutoff).order_by("-created_at", "-id")
        page = int(self.request.GET.get("hist_page", "1") or 1)
        page_size = 3
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)
        total_pages = paginator.num_pages or 1
        window = 5
        start_page = max(1, page_obj.number - window // 2)
        end_page = min(total_pages, start_page + window - 1)
        start_page = max(1, end_page - window + 1)
        return {
            "referencing_history_page": list(page_obj.object_list),
            "referencing_history_page_number": page_obj.number,
            "referencing_total_pages": total_pages,
            "referencing_page_numbers": list(range(start_page, end_page + 1)),
        }

    def cost_func(self, data):
        return get_section_cost(self.step_key) or Decimal("1")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        store = _get_global_store(self.request)
        context["reference_content"] = store.get("referencing_input_content", "")
        context["reference_style"] = store.get("referencing_input_style", "APA 7")
        context["reference_count"] = store.get("referencing_input_count", "")
        context["referencing_history_enabled"] = True
        context.update(self._paginate_history())
        return context

    def post(self, request, *args, **kwargs):
        store = _get_global_store(request)
        content_text = (request.POST.get("content_input") or "").strip()
        reference_style = (request.POST.get("reference_style") or "").strip() or "APA 7"
        reference_count_raw = (request.POST.get("reference_count") or "").strip()
        additional_notes = (request.POST.get("instruction") or "").strip()
        coupon_code = (request.POST.get("coupon_code") or "").strip()
        cutoff = timezone.now() - datetime.timedelta(days=30)
        ReferencingHistory.objects.filter(user=request.user, created_at__lt=cutoff).delete()

        try:
            reference_count = int(reference_count_raw)
        except (TypeError, ValueError):
            reference_count = 0

        if not content_text:
            messages.error(request, "Content is required for referencing.")
            ctx = self.get_context_data(**kwargs)
            ctx.update(
                {
                    "reference_content": content_text,
                    "reference_style": reference_style,
                    "reference_count": reference_count_raw,
                }
            )
            return self.render_to_response(ctx)

        if reference_count <= 0:
            messages.error(request, "Please provide how many references to include (use a number greater than 0).")
            ctx = self.get_context_data(**kwargs)
            ctx.update(
                {
                    "reference_content": content_text,
                    "reference_style": reference_style,
                    "reference_count": reference_count_raw,
                }
            )
            return self.render_to_response(ctx)

        cost = self.cost_func({"instruction": additional_notes})
        account = ensure_gems_account(request.user, "Welcome bonus")
        coupon, net_cost, discount, status, warning = _apply_coupon(
            request.user, ContentSectionType.REFERENCING, cost, code=coupon_code
        )
        if status != "ok":
            messages.error(request, "Coupon not applicable to this task.")
            ctx = self.get_context_data(**kwargs)
            ctx.update(
                {
                    "reference_content": content_text,
                    "reference_style": reference_style,
                    "reference_count": reference_count_raw,
                }
            )
            return self.render_to_response(ctx)
        if account.balance < net_cost:
            messages.error(request, f"Not enough gems for this generation (needs {net_cost}).")
            return redirect(request.path)
        if net_cost > 0:
            account.balance -= net_cost
            account.save(update_fields=["balance"])
            GemTransaction.objects.create(
                user=request.user,
                amount=-net_cost,
                reason="Global Referencing generation",
                created_by=request.user,
            )
        if coupon and discount > 0:
            CouponRedemption.objects.create(
                coupon=coupon,
                user=request.user,
                task_type=ContentSectionType.REFERENCING,
                gems_discounted=discount,
            )

        prompt = (
            "You are an academic referencing assistant. Insert in-text citations into the user's content without changing"
            " their wording, then provide a complete reference list. All references must be real, recent, and verifiable"
            " (journals, books, authoritative reports or reputable sites). Strictly use sources published 2021 or later"
            " (prefer 2021–2025) and replace any older classic citations with newer peer-reviewed updates or meta-reviews."
            f"\n\nReferencing style: {reference_style}"
            f"\nNumber of distinct references: exactly {reference_count}"
            "\nRules:"
            "\n- Keep every sentence and heading unchanged; only add citations where relevant."
            "\n- Do NOT place citations inside the Introduction or Conclusion sections."
            "\n- Match the citation format and reference list format to the chosen style (e.g., Harvard/APA author-date,"
            " MLA author-page, Chicago author-date, IEEE numbered)."
            "\n- Provide exactly the requested number of unique references, and use the same count of in-text citations."
            "\n- Each in-text citation must correspond to one item in the reference list (one-to-one)."
            "\n- Prioritize peer-reviewed or reputable sources and avoid placeholders."
            "\n- If a DOI or stable URL exists, include it in the reference entry."
        )
        if additional_notes:
            prompt += f"\n\nAdditional user notes:\n{additional_notes}"
        prompt += "\n\nUSER CONTENT (add citations to this without rewriting):\n" + content_text
        prompt += (
            "\n\nOUTPUT FORMAT (plain text):"
            "\nCITED CONTENT:\n<original content with inline citations>"
            "\n\nREFERENCES:\n<reference list aligned to the chosen style>"
        )

        try:
            output = _generate_with_gemini(prompt.strip(), fallback="References could not be generated.")
        except Exception:
            output = "References could not be generated."

        store[self.step_key] = output
        store["referencing_input_content"] = content_text
        store["referencing_input_style"] = reference_style
        store["referencing_input_count"] = reference_count_raw
        _save_global_store(request, store)
        ReferencingHistory.objects.create(
            user=request.user,
            content_input=content_text,
            reference_style=reference_style,
            reference_count=reference_count,
            result=output,
        )
        messages.success(
            request,
            f"{self.title} generated. {net_cost} gems deducted. Remaining balance: {account.balance}."
            + (f" Coupon {coupon.code} applied (-{discount} gems)." if coupon and discount else "")
        )
        return redirect(request.path)


class GlobalPlagView(GlobalStepBase):
    step_key = ContentSectionType.PLAG_REPORT
    title = "Plag Report"
    next_url = reverse_lazy("marketing:global_ai")

    def cost_func(self, data):
        return Decimal("3")


class GlobalAIView(GlobalStepBase):
    step_key = ContentSectionType.AI_REPORT
    title = "AI Report"
    next_url = reverse_lazy("marketing:global_full")

    def cost_func(self, data):
        return Decimal("3")


class GlobalFullView(GlobalStepBase):
    step_key = ContentSectionType.FULL_CONTENT
    title = "Full Content"
    next_url = None

    def cost_func(self, data):
        return get_section_cost(self.step_key) or Decimal("5")


class GlobalMonsterView(GlobalAccessMixin, TemplateView):
    template_name = "marketing/global_monster.html"

    def post(self, request, *args, **kwargs):
        store = _get_global_store(request)
        account = ensure_gems_account(request.user, "Welcome bonus")
        cost = get_monster_cost()
        coupon, net_cost, discount, status, warning = _apply_coupon(
            request.user, ContentSectionType.MONSTER, cost, code=request.POST.get("coupon_code")
        )
        if status != "ok":
            messages.error(request, "Coupon not applicable to this task.")
            return redirect(request.path)
        if account.balance < net_cost:
            messages.error(request, f"Not enough gems for Monster generation (needs {net_cost}).")
            return redirect(request.path)
        account.balance -= net_cost
        account.save(update_fields=["balance"])
        GemTransaction.objects.create(
            user=request.user,
            amount=-net_cost,
            reason="Monster generation",
            created_by=request.user,
        )
        if coupon and discount > 0:
            CouponRedemption.objects.create(
                coupon=coupon,
                user=request.user,
                task_type=ContentSectionType.MONSTER,
                gems_discounted=discount,
            )
        instruction = request.POST.get("instruction", "").strip()
        attachment_text = _extract_text_from_uploads(request.FILES.getlist("attachments"))
        combined = instruction
        if attachment_text:
            combined += "\n\nAttached text (best-effort extraction):\n" + attachment_text

        prompt = (
            "You are Monster Click. Return only the final cited content and a reference list—no outline, no extra commentary.\n"
            "- Analyze the instruction and attachments.\n"
            "- Write the full content with in-text citations. Match the word count specified in the instruction/structure as closely as possible. "
            "If no count given, target a concise 800–1200 words.\n"
            "- References: per 1000 words, include 7 sources (4 journals, 3 books). Use publication years 2021–2025 only. "
            "Citations must align with the referencing style mentioned (default APA).\n"
            "- Reference list at the end must correspond to in-text citations and look credible; avoid placeholder or obviously fake entries.\n"
            "Return plain text: first the content, then a 'References' section.\n\nUSER REQUEST AND CONTEXT:\n"
            f"{combined}"
        )

        try:
            monster_content = _generate_with_gemini(prompt, fallback="Monster content could not be generated.")
        except Exception:
            monster_content = "Monster content could not be generated."

        # keep only the content in the store for display
        store.clear()
        store[ContentSectionType.CONTENT] = monster_content
        _save_global_store(request, store)
        MonsterHistory.objects.create(
            user=request.user,
            instruction=instruction,
            result=monster_content,
        )
        messages.success(
            request,
            f"Monster generation completed. {net_cost} gems deducted. Remaining balance: {account.balance}."
            + (f" Coupon {coupon.code} applied (-{discount} gems)." if coupon and discount else ""),
        )
        return redirect(request.path)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        store = _get_global_store(self.request)
        account = ensure_gems_account(self.request.user, "Welcome bonus")
        context["gems_balance"] = account.balance
        context["monster_cost"] = get_monster_cost()
        context["monster_content"] = store.get(ContentSectionType.CONTENT)
        if not context["monster_content"]:
            latest = MonsterHistory.objects.filter(user=self.request.user).order_by("-created_at").first()
            if latest:
                context["monster_content"] = latest.result
        qs = MonsterHistory.objects.filter(user=self.request.user).order_by("-created_at", "-id")
        page = int(self.request.GET.get("hist_page", "1") or 1)
        paginator = Paginator(qs, 3)
        page_obj = paginator.get_page(page)
        context["history_page"] = list(page_obj.object_list)
        context["history_page_number"] = page_obj.number
        total_pages = paginator.num_pages or 1
        window = 5
        start_page = max(1, page_obj.number - window // 2)
        end_page = min(total_pages, start_page + window - 1)
        start_page = max(1, end_page - window + 1)
        context["history_total_pages"] = total_pages
        context["history_page_numbers"] = list(range(start_page, end_page + 1))
        return context
class SectionDetailView(MarketingAccessMixin, DetailView):
    """Dedicated page per section for generation/approval."""

    model = Job
    template_name = "marketing/section_detail.html"
    context_object_name = "job"

    SECTION_MAP = {
        "summary": ContentSectionType.SUMMARY,
        "structure": ContentSectionType.STRUCTURE,
        "content": ContentSectionType.CONTENT,
        "referencing": ContentSectionType.REFERENCING,
        "plag-report": ContentSectionType.PLAG_REPORT,
        "ai-report": ContentSectionType.AI_REPORT,
        "full-content": ContentSectionType.FULL_CONTENT,
    }

    def get_queryset(self):
        return Job.objects.filter(created_by=self.request.user)

    def get_section_type(self):
        slug = self.kwargs.get("section")
        return self.SECTION_MAP.get(slug)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        section_type = self.get_section_type()
        job = context["job"]
        section = job.sections.filter(section_type=section_type).first()
        context["section_obj"] = section
        context["section_slug"] = self.kwargs.get("section")
        context["section_label"] = dict(ContentSectionType.choices).get(section_type, "Section")
        context["attachments"] = job.attachments.all()
        if self.request.user.role == User.Role.GLOBAL:
            account = ensure_gems_account(self.request.user, "Welcome bonus")
            context["gems_balance"] = account.balance
            context["section_cost"] = get_section_cost(section_type)
        return context

class DashboardView(MarketingAccessMixin, TemplateView):
    template_name = "marketing/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        jobs = list(
            Job.objects.filter(created_by=self.request.user).order_by(
                "-created_at"
            )
        )
        pending_jobs_total = len(
            [job for job in jobs if not job.is_superadmin_approved and not job.is_deleted]
        )
        jobs = [job for job in jobs if not job.is_deleted]
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            jobs = self._filter_jobs(jobs, search_query)
        recent_jobs = jobs[:5]
        context["cards"] = get_job_cards_for_user(self.request.user)
        context["table"] = self._build_table(recent_jobs)
        context["search_query"] = search_query
        context["jobs_page_obj"] = None
        context["jobs_paginator"] = None
        self.request.session["seen_marketing_new_jobs"] = pending_jobs_total
        return context

    def _filter_jobs(self, jobs, query):
        q = query.lower()
        filtered = []
        for job in jobs:
            if (
                q in (job.job_id_customer or "").lower()
                or q in (job.system_id or "").lower()
                or q in (job.instruction or "").lower()
            ):
                filtered.append(job)
        return filtered

    def _build_table(self, jobs):
        rows = []
        for idx, job in enumerate(jobs, start=1):
            rows.append(
                [
                    idx,
                    job.job_id_customer,
                    job.system_id,
                    format_currency(job.amount_inr),
                    localize_deadline(job.expected_deadline),
                    localize_deadline(job.strict_deadline),
                    f'<a class="btn btn-sm btn-outline-primary" href="{reverse_lazy("marketing:job_detail", args=[job.pk])}">View</a>',
                    self._delete_button(job),
                ]
            )
        return {
            "headers": [
                "SL No",
                "Job ID",
                "System ID",
                "Amount",
                "Expected Deadline",
                "Strict Deadline",
                "View Job",
                "Delete",
            ],
            "rows": rows,
            "empty_message": "No jobs captured yet.",
        }

    def _delete_button(self, job):
        if job.is_deleted:
            return '<span class="badge text-bg-secondary">Deleted</span>'
        url = reverse_lazy("marketing:job_delete", args=[job.pk])
        return f'<a class="btn btn-sm btn-outline-danger" href="{url}">Delete</a>'


class AllProjectsView(MarketingAccessMixin, TemplateView):
    template_name = "marketing/all_projects.html"
    SECTION_SEQUENCE = [
        ContentSectionType.SUMMARY,
        ContentSectionType.STRUCTURE,
        ContentSectionType.CONTENT,
        ContentSectionType.REFERENCING,
        ContentSectionType.PLAG_REPORT,
        ContentSectionType.AI_REPORT,
        ContentSectionType.FULL_CONTENT,
    ]

    def _parse_date(self, value):
        try:
            return datetime.date.fromisoformat(value)
        except Exception:
            return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_param = self.request.GET.get("filter", "all")
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
            Job.objects.filter(created_by=self.request.user, created_at__gte=start_dt, created_at__lt=end_dt)
        )
        pending_total = len(
            [job for job in jobs if not job.is_superadmin_approved and not job.is_deleted]
        )
        jobs = [job for job in jobs if not job.is_deleted]
        if filter_param == "pending":
            jobs = [job for job in jobs if not job.is_superadmin_approved]
        elif filter_param == "amount":
            jobs = sorted(
                jobs,
                key=lambda job: job.amount_inr.to_decimal()
                if hasattr(job.amount_inr, "to_decimal")
                else job.amount_inr or 0,
                reverse=True,
            )
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            jobs = [
                job
                for job in jobs
                if search_query.lower() in (job.job_id_customer or "").lower()
                or search_query.lower() in (job.system_id or "").lower()
                or search_query.lower() in (job.instruction or "").lower()
            ]
        from django.core.paginator import Paginator

        paginator = Paginator(jobs, 5)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        page_jobs = page_obj.object_list

        context["filter"] = filter_param
        context["search_query"] = search_query
        context["table"] = self._build_table(page_jobs, start_index=page_obj.start_index())
        context["cards"] = get_job_cards_for_user(self.request.user)
        context["page_obj"] = page_obj
        context["paginator"] = paginator
        context["start_date"] = start_date
        context["end_date"] = end_date
        base_query = self.request.GET.copy()
        if "page" in base_query:
            base_query.pop("page")
        context["base_query"] = base_query.urlencode()
        self.request.session["seen_marketing_new_jobs"] = pending_total
        return context

    def _build_table(self, jobs, start_index=1):
        rows = []
        section_headers = [section.label for section in self.SECTION_SEQUENCE]
        for idx, job in enumerate(jobs, start=start_index):
            rows.append(
                [
                    idx,
                    job.job_id_customer,
                    job.system_id,
                    format_currency(job.amount_inr),
                    localize_deadline(job.expected_deadline),
                    localize_deadline(job.strict_deadline),
                    f'<a class="btn btn-sm btn-outline-primary" href="{reverse("marketing:job_detail", args=[job.pk])}">View</a>',
                    *[self._section_cell(job, section) for section in self.SECTION_SEQUENCE],
                ]
            )
        return {
            "headers": [
                "SL No",
                "Job ID",
                "System ID",
                "Amount",
                "Expected Deadline",
                "Strict Deadline",
                "View Job",
                *section_headers,
            ],
            "rows": rows,
            "empty_message": "No projects matching filter.",
        }

    def _section_cell(self, job, section_type):
        section = job.sections.filter(section_type=section_type).first()
        if not section:
            return '<span class="badge text-bg-secondary">Pending</span>'
        if section.status != ContentStatus.APPROVED:
            return (
                '<span class="badge text-bg-secondary" title="Awaiting approval">'
                "Blurred"
                "</span>"
            )
        url = f'{reverse("marketing:job_detail", args=[job.pk])}?section={section_type}'
        return f'<a class="btn btn-sm btn-outline-primary" href="{url}">View</a>'


class JobDropView(MarketingAccessMixin, FormView):
    template_name = "marketing/job_drop_form.html"
    form_class = JobDropForm
    success_url = reverse_lazy("marketing:all_projects")
    management_system_key = ManagementSystem.Keys.FORM

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_account_approved:
            messages.warning(
                request,
                "Account pending approval. You cannot create jobs yet.",
            )
            return redirect("common:welcome")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Job created successfully.")
        return super().form_valid(form)


class JobDetailView(MarketingAccessMixin, DetailView):
    template_name = "marketing/job_detail.html"
    model = Job
    context_object_name = "job"

    def get_queryset(self):
        return Job.objects.filter(created_by=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job = context["job"]
        visited = set(self.request.session.get("visited_job_ids", []))
        if job.pk not in visited:
            visited.add(job.pk)
            self.request.session["visited_job_ids"] = list(visited)
        # Gems balance for global users
        if self.request.user.role == User.Role.GLOBAL:
            account = ensure_gems_account(self.request.user, "Ensure balance")
            context["gems_balance"] = account.balance
        sections = []
        sequence = [c[0] for c in ContentSectionType.choices]
        for idx, section_value in enumerate(sequence):
            section = job.sections.filter(section_type=section_value).first()
            if section:
                section.viewable = True  # marketing owner can always view
                # gate: previous section must be approved
                if idx == 0:
                    section.prev_approved = True
                else:
                    prev_type = sequence[idx - 1]
                    prev_section = job.sections.filter(section_type=prev_type).first()
                    section.prev_approved = prev_section and prev_section.status == ContentStatus.APPROVED
                # Build fixed slots: 1, 2, 3 generation attempts + Approved slot
                history_entries = list(section.histories.order_by("created_at"))  # oldest first

                def _placeholder(label):
                    return SimpleNamespace(
                        action=label,
                        content=f"Not yet {label.lower()}.",
                        created_at=None,
                        is_placeholder=True,
                        approved=False,
                    )

                slots = [_placeholder("Generated") for _ in range(3)]

                # place previous contents into slots 0..n-1
                for i in range(min(len(history_entries), 3)):
                    entry = history_entries[i]
                    slots[i] = SimpleNamespace(
                        action=f"Gen {i+1}",
                        content=entry.content,
                        created_at=entry.created_at,
                        is_placeholder=False,
                        approved=False,
                    )

                # determine current attempt index (1-based) from regeneration_count; ensure >=1 if content exists
                attempt = section.regeneration_count
                if section.content and attempt == 0:
                    attempt = 1
                attempt = max(1, min(attempt, 3))
                # place current content into its slot
                if section.content:
                    idx = attempt - 1
                    slots[idx] = SimpleNamespace(
                        action=f"Gen {attempt}",
                        content=section.content,
                        created_at=section.updated_at,
                        is_placeholder=False,
                        approved=section.status == ContentStatus.APPROVED,
                    )

                # Approved slot uses current content if approved, else placeholder
                if section.status == ContentStatus.APPROVED and section.content:
                    approved_slot = SimpleNamespace(
                        action="Approved",
                        content=section.content,
                        created_at=section.updated_at,
                        is_placeholder=False,
                        approved=True,
                    )
                else:
                    approved_slot = _placeholder("Approved")
                section.history_display = slots + [approved_slot]
                sections.append(section)
        context["sections"] = sections
        context["attachments"] = job.attachments.all()
        return context


class MarketingSectionActionView(MarketingAccessMixin, View):
    """Allow marketing owners to generate/regenerate/approve their own sections."""

    AI_PLAG_SET = {
        ContentSectionType.AI_REPORT,
        ContentSectionType.PLAG_REPORT,
    }
    GENERATION_ORDER = [
        ContentSectionType.SUMMARY,
        ContentSectionType.STRUCTURE,
        ContentSectionType.CONTENT,
        ContentSectionType.REFERENCING,
        ContentSectionType.PLAG_REPORT,
        ContentSectionType.AI_REPORT,
        ContentSectionType.FULL_CONTENT,
    ]

    def _charge_gems(self, user, amount, reason):
        if amount <= 0:
            return True
        account = ensure_gems_account(user, "Welcome bonus")
        if account.balance < amount:
            return False
        account.balance -= amount
        account.save(update_fields=["balance"])
        GemTransaction.objects.create(
            user=user, amount=-amount, reason=reason, created_by=user
        )
        return True

    def _previous_section_approved(self, section):
        sequence = [c[0] for c in ContentSectionType.choices]
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
        redirect_url = request.META.get("HTTP_REFERER") or reverse("marketing:all_projects")
        if not form.is_valid():
            messages.error(request, "Invalid action.")
            return redirect(redirect_url)

        section = get_object_or_404(
            JobContentSection, pk=form.cleaned_data["section_id"]
        )
        if section.job.created_by != request.user:
            messages.error(request, "You can only manage your own jobs.")
            return redirect(redirect_url)

        action = form.cleaned_data["action"]

        if (
            action in {"approve", "regenerate"}
            and request.user.role != User.Role.GLOBAL
            and not self._previous_section_approved(section)
        ):
            messages.error(
                request,
                "Complete the previous section before processing this one.",
            )
            return redirect(redirect_url)

        # Monster click: generate all sections in order (Global only)
        if action == "monster":
            if request.user.role != User.Role.GLOBAL:
                messages.error(request, "Monster action is only for global users.")
                return redirect(redirect_url)
            if not self._charge_gems(request.user, MONSTER_GEM_COST, "Monster generation"):
                messages.error(request, "Not enough gems for Monster generation (10 required).")
                return redirect(redirect_url)
            for stype in self.GENERATION_ORDER:
                sec = section.job.sections.filter(section_type=stype).first()
                if not sec:
                    continue
                if sec.section_type in self.AI_PLAG_SET:
                    sec.content = "AI/Plag Report not available."
                    sec.status = ContentStatus.REGENERATE
                    sec.save(update_fields=["content", "status", "updated_at"])
                    continue
                sec.add_history(action="monster")
                sec.content = self._generate_section_content(sec, regenerate=sec.regeneration_count > 0)
                sec.regeneration_count = max(sec.regeneration_count, 1)
                sec.status = ContentStatus.REGENERATE
                sec.save(
                    update_fields=["content", "regeneration_count", "status", "updated_at"]
                )
            sync_job_approval(section.job)
            messages.success(request, "Monster generation completed (10 gems deducted).")
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
                # Charge gems for first-time generation for global users
                if (
                    request.user.role == User.Role.GLOBAL
                    and section.regeneration_count == 0
                ):
                    cost = get_section_cost(section.section_type)
                    if cost > 0 and not self._charge_gems(
                        request.user, cost, f"Generate {section.get_section_type_display()}"
                    ):
                        messages.error(request, f"Not enough gems to generate {section.get_section_type_display()} (cost {cost}).")
                        return redirect(redirect_url)
                section.add_history(action="regenerate")
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
                    # charge if first generation happens during approval for global users
                    if request.user.role == User.Role.GLOBAL and section.regeneration_count == 0:
                        cost = get_section_cost(section.section_type)
                        if cost > 0 and not self._charge_gems(
                            request.user, cost, f"Generate {section.get_section_type_display()}"
                        ):
                            messages.error(request, f"Not enough gems to generate {section.get_section_type_display()} (cost {cost}).")
                            return redirect(redirect_url)
                    section.content = self._generate_section_content(section, regenerate=False)
                    if section.regeneration_count == 0:
                        section.regeneration_count = 1
                # store last version before locking in approval
                section.add_history(action="approve")
                section.status = ContentStatus.APPROVED
                section.save(update_fields=["content", "status", "updated_at"])
                sync_job_approval(section.job)
                messages.success(request, "Section approved.")
        else:
            messages.error(request, "Unknown action.")
        return redirect(redirect_url)


class DeletedJobsView(MarketingAccessMixin, TemplateView):
    template_name = "marketing/deleted_jobs.html"

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

        jobs_qs = Job.objects.filter(
            created_by=self.request.user,
            is_deleted=True,
            deleted_at__gte=start_dt,
            deleted_at__lt=end_dt,
        )
        jobs = sorted(jobs_qs, key=lambda job: job.deleted_at or timezone.now(), reverse=True)
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            q = search_query.lower()
            jobs = [
                job
                for job in jobs
                if q in (job.job_id_customer or "").lower()
                or q in (job.system_id or "").lower()
                or q in (job.instruction or "").lower()
            ]

        paginator = Paginator(jobs, 10)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["jobs"] = list(page_obj.object_list)
        context["page_obj"] = page_obj
        context["paginator"] = paginator
        context["search_query"] = search_query
        context["start_date"] = start_date
        context["end_date"] = end_date
        base_query = self.request.GET.copy()
        if "page" in base_query:
            base_query.pop("page")
        context["base_query"] = base_query.urlencode()
        self.request.session["seen_marketing_deleted_jobs"] = len(jobs_qs)
        return context


class MarketingJobDeleteView(MarketingAccessMixin, FormView):
    template_name = "marketing/job_delete.html"
    form_class = JobDeleteForm

    def dispatch(self, request, *args, **kwargs):
        self.job = Job.objects.filter(
            pk=kwargs["pk"], created_by=request.user, is_deleted__in=[False]
        ).first()
        if not self.job:
            messages.error(request, "Job not found or already deleted.")
            return redirect("marketing:deleted_jobs")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["job"] = self.job
        return context

    def form_valid(self, form):
        self.job.mark_deleted(self.request.user, form.cleaned_data["notes"])
        messages.info(self.request, "Job deleted successfully.")
        return redirect("marketing:deleted_jobs")


class HistoryView(MarketingAccessMixin, TemplateView):
    template_name = "marketing/history.html"

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

        jobs = Job.objects.filter(
            created_by=self.request.user,
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        ).order_by("-created_at")
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            q = search_query.lower()
            jobs = [
                job
                for job in jobs
                if q in (job.job_id_customer or "").lower()
                or q in (job.system_id or "").lower()
                or q in (job.instruction or "").lower()
            ]

        paginator = Paginator(jobs, 10)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["jobs"] = list(page_obj.object_list)
        context["page_obj"] = page_obj
        context["paginator"] = paginator
        context["search_query"] = search_query
        context["start_date"] = start_date
        context["end_date"] = end_date
        # base query for pagination links
        base_query = self.request.GET.copy()
        if "page" in base_query:
            base_query.pop("page")
        context["base_query"] = base_query.urlencode()
        return context


class HolidayListView(MarketingAccessMixin, TemplateView):
    template_name = "marketing/holidays.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["holidays"] = Holiday.objects.order_by("date")
        return context
