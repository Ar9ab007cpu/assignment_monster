from django import template

register = template.Library()


@register.filter
def getattr(value, arg):
    """Safe getattr/dict lookup for tables."""
    if not arg:
        return value
    if isinstance(value, dict):
        return value.get(arg)
    return getattr(value, arg, None)
