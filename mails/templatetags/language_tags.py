from django import template
from django.utils.translation import get_language

register = template.Library()

FLAGS = {
    "de": "🇩🇪",
    "fr": "🇫🇷",
    "en": "🇬🇧",
}


@register.simple_tag
def language_flag(code=None):
    """Flag emoji for a language code (defaults to the active language)."""
    code = code or get_language()
    return FLAGS.get(code.split("-")[0], "🏳️")
