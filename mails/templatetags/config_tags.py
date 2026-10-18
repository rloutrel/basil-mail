from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def prepend(value, prefix):
    return "%s%s" % (prefix, value)


@register.filter
def letter(index):
    """1 -> A, 2 -> B, ..."""
    return chr(ord("A") + int(index) - 1)
