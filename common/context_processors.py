"""Context processors shared across templates."""

from accounts.models import (
    FloorSignupRequest,
    GemsAccount,
    ProfileUpdateRequest,
    User,
)
from jobs.models import Job

from .system_control import get_management_system_map

try:
    from navbuilder.models import NavigationItem
except Exception:
    NavigationItem = None


def _unread_count(request, actual, session_key):
    seen = request.session.get(session_key, 0)
    if seen > actual:
        request.session[session_key] = actual
        seen = actual
    return max(actual - seen, 0)


def global_counts(request):
    """Expose notification badges for nav/sidebars."""

    counts = {
        "marketing": {"new_jobs": 0, "deleted_jobs": 0},
        "superadmin": {
            "new_jobs": 0,
            "user_approvals": 0,
            "profile_requests": 0,
            "floor_signups": 0,
        },
    }

    user = getattr(request, "user", None)
    is_auth = bool(user and getattr(user, "is_authenticated", False))
    is_global = bool(
        is_auth and getattr(user, "role", None) == User.Role.GLOBAL
    )
    visited_jobs = set(request.session.get("visited_job_ids", []))
    data = {
        "nav_counts": counts,
        "management_systems": get_management_system_map(user),
        "gems_balance": None,
        "is_global_user": is_global,
    }
    if not user or not user.is_authenticated:
        return data

    if user.role == User.Role.MARKETING:
        base_jobs = list(Job.objects.filter(created_by=user))
        pending_jobs = len(
            [
                job
                for job in base_jobs
                if not job.is_superadmin_approved
                and not job.is_deleted
                and job.pk not in visited_jobs
            ]
        )
        counts["marketing"]["new_jobs"] = _unread_count(
            request, pending_jobs, "seen_marketing_new_jobs"
        )
        deleted_jobs = len([job for job in base_jobs if job.is_deleted])
        counts["marketing"]["deleted_jobs"] = _unread_count(
            request, deleted_jobs, "seen_marketing_deleted_jobs"
        )
    elif user.role in {User.Role.SUPER_ADMIN, User.Role.CO_SUPER_ADMIN}:
        jobs = list(Job.objects.all())
        new_jobs = [
            job
            for job in jobs
            if not job.is_superadmin_approved and not job.is_deleted and job.pk not in visited_jobs
        ]
        counts["superadmin"]["new_jobs"] = _unread_count(
            request, len(new_jobs), "seen_superadmin_new_jobs"
        )
        pending_users = [
            marketing_user
            for marketing_user in User.objects.filter(role=User.Role.MARKETING)
            if marketing_user.is_active and not marketing_user.is_account_approved
        ]
        counts["superadmin"]["user_approvals"] = _unread_count(
            request, len(pending_users), "seen_superadmin_user_approvals"
        )
        pending_floor = FloorSignupRequest.objects.filter(
            status=FloorSignupRequest.Status.PENDING
        ).count()
        counts["superadmin"]["floor_signups"] = _unread_count(
            request, pending_floor, "seen_superadmin_floor_signups"
        )
        profile_requests = [
            prof_request
            for prof_request in ProfileUpdateRequest.objects.all()
            if prof_request.status == ProfileUpdateRequest.Status.PENDING
        ]
        counts["superadmin"]["profile_requests"] = _unread_count(
            request, len(profile_requests), "seen_superadmin_profile_requests"
        )

    if NavigationItem:
        nav_items = list(
            NavigationItem.objects.filter(role=user.role, is_active=True).order_by(
                "order", "id"
            )
        )
        data["nav_items"] = nav_items

    # lightweight check for available gems so global sidebar can display balance
    try:
        balance = (
            GemsAccount.objects.filter(user=user)
            .values_list("balance", flat=True)
            .first()
        )
    except Exception:
        balance = None
    data["gems_balance"] = balance

    return data
