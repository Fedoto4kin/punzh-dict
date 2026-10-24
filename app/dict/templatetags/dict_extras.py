import re

from django import template
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

from ..helpers import normalization
from ..see_audit import link_deriv_lemmas, link_see_lemmas
from ..tag_highlight import highlight_tags as highlight_tags_html

register = template.Library()


@register.filter
def link_ontology_themes(text, fields):
    """Turn SemanticField names in axes_display into /ontology/<id>/ links."""
    if not text:
        return ""
    escaped = escape(text)
    if not fields:
        return mark_safe(escaped)
    # Longest names first so shorter substrings do not break longer labels.
    ordered = sorted(
        (f for f in fields if f.get("id") and f.get("name")),
        key=lambda f: len(f["name"]),
        reverse=True,
    )
    for f in ordered:
        name = escape(f["name"])
        href = reverse("ontology_field", args=[f["id"]])
        escaped = escaped.replace(name, f'<a href="{escape(href)}">{name}</a>')
    return mark_safe(escaped)


@register.filter
def nice(text):
    # TODO: only in <b> tags
    return re.sub(
        r"([\|]{1,2})", r'<span class="text-muted font-weight-normal">\1</span>', text
    )


@register.filter
def clear(text):
    return normalization(text)


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def highlight_rus(text):
    return re.sub(r"([А-Яа-яЁё]+)", r'<span class="text-rus">\1</span>', text)


@register.filter
def highlight_tags(text):
    return highlight_tags_html(text)


@register.filter
def make_link(text):
    return link_deriv_lemmas(link_see_lemmas(text))


@register.filter
def make_break(text):
    return re.sub(r"(◊)", r"<hr/>\1", text)


@register.filter
def pluralize_words(count):
    """
    Кастомный фильтр для склонения слова "слово" в зависимости от числа.
    """
    if not isinstance(count, int):
        return f"{count} слов"  # Если передано не число, возвращаем форму по умолчанию

    last_digit = count % 10
    last_two_digits = count % 100

    if last_digit == 1 and last_two_digits != 11:
        return f"<b>{count}</b> слово"
    elif 2 <= last_digit <= 4 and not (12 <= last_two_digits <= 14):
        return f"<b>{count}</b> слова"
    else:
        return f"<b>{count}</b> слов"


# @register.filter
# def make_link(word):
#     return word.split(',')[0]
