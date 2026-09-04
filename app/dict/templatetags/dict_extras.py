import re

from django import template

from ..helpers import normalization
from ..see_audit import link_deriv_lemmas, link_see_lemmas

register = template.Library()


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
