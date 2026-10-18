from urllib.parse import urlencode

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring_with(context, **overrides):
    """Rebuild the current query string, preserving filters, with overrides."""
    params = context["request"].GET.copy()
    for key, value in overrides.items():
        params[key] = value
    for key in list(params.keys()):
        if params[key] in ("", None):
            del params[key]
    return urlencode(params)
