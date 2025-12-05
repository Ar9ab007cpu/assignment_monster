"""Custom template tags for reusable formatting."""

from django import template
from django.db import models
from django.utils import timezone
from django.core.cache import cache
import re
import datetime
from types import SimpleNamespace

from common.utils import format_currency, localize_deadline

register = template.Library()


@register.filter
def currency(value):
    return format_currency(value)


@register.filter
def deadline(value):
    return localize_deadline(value)


@register.filter
def dict_get(value, key):
    """Fetch dict entry safely inside templates."""

    if isinstance(value, dict):
        return value.get(key)
    return None


@register.filter
def browser_name(user_agent):
    """Small UA parser to extract browser family + version."""
    if not user_agent:
        return "Unknown"
    ua = str(user_agent).lower()
    def match(pattern):
        m = re.search(pattern, ua)
        return m.group(1) if m else ""

    if "edg" in ua:
        ver = match(r"edg/([\d\.]+)")
        return f"Edge {ver}" if ver else "Edge"
    if "opr" in ua or "opera" in ua:
        ver = match(r"(?:opr|opera)/([\d\.]+)")
        return f"Opera {ver}" if ver else "Opera"
    if "chrome" in ua and "safari" in ua:
        ver = match(r"chrome/([\d\.]+)")
        return f"Chrome {ver}" if ver else "Chrome"
    if "safari" in ua and "chrome" not in ua:
        ver = match(r"version/([\d\.]+)")
        return f"Safari {ver}" if ver else "Safari"
    if "firefox" in ua:
        ver = match(r"firefox/([\d\.]+)")
        return f"Firefox {ver}" if ver else "Firefox"
    if "msie" in ua or "trident" in ua:
        ver = match(r"(?:msie |rv:)([\d\.]+)")
        return f"Internet Explorer {ver}" if ver else "Internet Explorer"
    return user_agent


@register.simple_tag
def active_notices(user):
    """Return active notices (no user filtering)."""
    from common.models import Notice

    try:
        notices = list(Notice.active_for_user(user))
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
        return notices
    except Exception:
        # Fail safe if DB not migrated or backend errors
        cached = cache.get("fallback_notices", [])
        results = []
        now = timezone.now()
        for n in cached:
            # Apply the same active window logic
            if not n.get("is_active"):
                continue
            start_at = n.get("start_at")
            end_at = n.get("end_at")
            show_on_marketing = n.get("show_on_marketing", True)
            show_on_global = n.get("show_on_global", True)
            try:
                # cache stores datetimes already, but guard if strings
                if isinstance(start_at, str):
                    start_at = timezone.make_aware(datetime.datetime.fromisoformat(start_at))
                if isinstance(end_at, str):
                    end_at = timezone.make_aware(datetime.datetime.fromisoformat(end_at))
            except Exception:
                start_at = n.get("start_at")
                end_at = n.get("end_at")
            if start_at and now < start_at:
                continue
            if end_at and now > end_at:
                continue
            # Audience filter
            try:
                role = getattr(user, "role", None)
                Role = getattr(user, "Role", None)
                if Role and role == Role.MARKETING and not show_on_marketing:
                    continue
                if Role and role == Role.GLOBAL and not show_on_global:
                    continue
            except Exception:
                if not show_on_marketing:
                    continue
            results.append(SimpleNamespace(**n))
        return results
