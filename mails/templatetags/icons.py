from pathlib import Path

from django.utils.safestring import mark_safe

from django import template
from django.conf import settings

register = template.Library()

_cache = {}


@register.simple_tag
def bi_icon(name, css_class=""):
    """Inline the Bootstrap Icons SVG with the given name (MIT licensed,
    vendored under static/icons)."""
    name = (name or "").strip()
    if "/" in name or "\\" in name or not name:
        name = "envelope"
    if name not in _cache:
        path = Path(settings.BASE_DIR) / "static" / "icons" / f"{name}.svg"
        try:
            svg = path.read_text()
        except OSError:
            svg = (Path(settings.BASE_DIR) / "static" / "icons" / "envelope.svg").read_text()
        svg = svg.replace('class="bi ', 'class="bi icon-inline ')
        _cache[name] = svg
    svg = _cache[name]
    if css_class:
        svg = svg.replace('class="bi ', f'class="{css_class} bi ')
    return mark_safe(svg)
