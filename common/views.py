from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.utils import timezone

from common.models import Notice


@login_required
@require_POST
def dismiss_notice(request):
    notice_id = request.POST.get("notice_id")
    try:
        notice_id = int(notice_id)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False})
    dismissed = request.session.get("dismissed_notice_ids", [])
    if notice_id not in dismissed:
        dismissed.append(notice_id)
        request.session["dismissed_notice_ids"] = dismissed
    return JsonResponse({"ok": True})


def root_redirect(request):
    user = request.user
    if user.is_authenticated:
        role = getattr(user, "role", None)
        try:
            Role = user.Role
        except Exception:
            Role = None
        if role in {"super_admin", "co_super_admin"} or (Role and role in {Role.SUPER_ADMIN, Role.CO_SUPER_ADMIN}):
            return redirect("superadmin:welcome")
        if role == "marketing" or (Role and role == Role.MARKETING):
            return redirect("marketing:welcome")
    return redirect("accounts:login")
