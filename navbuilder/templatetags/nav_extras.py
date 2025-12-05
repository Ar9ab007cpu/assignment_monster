from django import template

register = template.Library()


@register.simple_tag
def nav_badge(nav_counts, path):
    """Fetch nested nav count using dot notation like 'marketing.new_jobs'."""
    if not nav_counts or not path:
        return 0
    parts = path.split(".")
    value = nav_counts
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = None
        if value is None:
            return 0
    return value or 0


@register.simple_tag(takes_context=True)
def nav_active_class(context, *targets):
    """
    Return 'active' if the current view/path matches any target.
    Targets can be Django view names (with namespace) or literal paths.
    """

    request = context.get("request")
    if not request:
        return ""

    match = getattr(request, "resolver_match", None)
    view_name = ""
    url_name = ""
    if match:
        view_name = getattr(match, "view_name", "") or ""
        url_name = getattr(match, "url_name", "") or ""
    path = getattr(request, "path", "") or ""

    for target in targets:
        if not target:
            continue
        if target.startswith("/"):
            if path == target or (target != "/" and path.startswith(target)):
                return "active"
        if target == view_name or target == url_name:
            return "active"
    return ""


MANAGEMENT_URLS = {
    "superadmin:system_control",
    "superadmin:form_management_list",
    "superadmin:holiday_management",
    "pagebuilder:templates",
}

MANAGEMENT_LABELS = {
    "system control",
    "form management",
    "holiday management",
    "page builder",
}


def _is_management_item(item):
    url_name = getattr(item, "url_name", "") or ""
    label = (getattr(item, "label", "") or "").lower()
    return url_name in MANAGEMENT_URLS or label in MANAGEMENT_LABELS


@register.filter
def management_only(nav_items):
    """Return only management/system-control oriented nav items."""
    if not nav_items:
        return []
    return [item for item in nav_items if _is_management_item(item)]


@register.filter
def non_management(nav_items):
    """Return nav items excluding management/system-control entries."""
    if not nav_items:
        return []
    return [item for item in nav_items if not _is_management_item(item)]
