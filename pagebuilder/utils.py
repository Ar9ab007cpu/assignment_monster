"""Helpers to render DB-backed marketing pages."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.template.loader import render_to_string
from django.db import DatabaseError

from jobs.services import get_job_cards_for_user
from .models import PageTemplate, PageBlock


@dataclass
class RenderedBlock:
    block: PageBlock
    data: Dict[str, Any]
    style: Dict[str, Any]
    animation_class: str


def _animation_class(block):
    animation = block.animation or getattr(block.template.theme, "animation", None)
    if not animation:
        return ""
    return animation.css_class or ""


def _dig(mapping, path):
    if not path:
        return None
    if "." not in path:
        return mapping.get(path)
    current = mapping
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def _normalize_data(block, user, context):
    data = block.data or {}
    data = dict(data)  # shallow copy

    source = data.get("source")
    key = data.get("key")

    if block.block_type == PageBlock.BlockType.CARD_LIST and source == "job_cards":
        data["cards"] = get_job_cards_for_user(user)

    elif block.block_type in {PageBlock.BlockType.TABLE, PageBlock.BlockType.STATS}:
        if source == "context" and key:
            data["rows"] = _dig(context, key) or []
        if source == "context" and data.get("columns_key"):
            data["columns"] = _dig(context, data["columns_key"]) or []

    elif block.block_type == PageBlock.BlockType.HERO:
        # allow headline/subhead placeholders
        if "{{user}}" in data.get("headline", ""):
            data["headline"] = data["headline"].replace(
                "{{user}}", getattr(user, "first_name", "") or user.email or ""
            )
    return data


def build_page(slug: str, user, context: Dict[str, Any]):
    """Return a render-ready page object or None."""

    try:
        template = PageTemplate.objects.filter(slug=slug).first()
    except Exception as exc:
        print(
            f"[pagebuilder] Failed to load template '{slug}': "
            f"{type(exc).__name__}: {exc!r} args={getattr(exc, 'args', None)}"
        )
        return None
    if not template:
        return None
    if not template.is_active:
        return None
    # Fallback: if pagebuilder was toggled off via templates, allow normal rendering paths.
    if not template.is_allowed_for(getattr(user, "role", None)):
        return None

    try:
        blocks_qs = template.blocks.all().order_by("area", "order", "id")
    except Exception as exc:
        print(
            f"[pagebuilder] Failed to load blocks for '{slug}': "
            f"{type(exc).__name__}: {exc!r} args={getattr(exc, 'args', None)}"
        )
        return None
    areas: Dict[str, List[RenderedBlock]] = defaultdict(list)
    for block in blocks_qs:
        if not block.is_active:
            continue
        rendered = RenderedBlock(
            block=block,
            data=_normalize_data(block, user, context),
            style=block.style or {},
            animation_class=_animation_class(block),
        )
        areas[block.area].append(rendered)

    return {
        "template": template,
        "theme": template.theme,
        "areas": areas,
    }


def render_page_to_html(slug: str, user, context: Dict[str, Any]) -> str:
    """Render a page slug directly to html string."""

    page = build_page(slug, user, context)
    if not page:
        return ""
    return render_to_string("pagebuilder/render_page.html", {"page": page})
