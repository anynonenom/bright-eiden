from django import template

register = template.Library()


@register.filter
def dict_get(d, key):
    """Return d[key] for use in templates: {{ mydict|dict_get:key }}"""
    if isinstance(d, dict):
        return d.get(key)
    return None
