"""Utility helpers shared across apps."""

from decimal import Decimal

from bson.decimal128 import Decimal128
from django.utils import timezone


def to_decimal(value):
    """Convert Mongo Decimal128 or other numeric values to Decimal."""

    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal128):
        value = value.to_decimal()
    try:
        return Decimal(value)
    except Exception:
        return Decimal("0")


def format_currency(amount):
    """Return a neatly formatted INR string."""

    return f"₹{to_decimal(amount):,.2f}"


def localize_deadline(value):
    """Ensure datetimes are timezone aware and human friendly."""

    if not value:
        return "-"
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return timezone.localtime(value).strftime("%d %b %Y %I:%M %p")
