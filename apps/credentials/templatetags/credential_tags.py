from django import template

register = template.Library()


@register.filter
def dict_key(d, key):
    """Return d[key] or empty string. Allows dict lookup in templates."""
    if isinstance(d, dict):
        return d.get(key, "")
    return ""
