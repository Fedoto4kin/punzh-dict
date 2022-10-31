import re
from django import template
from ..helpers import normalization

register = template.Library()

@register.filter
def nice(text):
    # TODO: only in <b> tags
    return re.sub(r'([\|]{1,2})', r'<span class="text-muted font-weight-normal">\1</span>', text)

@register.filter
def clear(text):
    return normalization(text)

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def highlight_rus(text):
    return re.sub(r'([А-Яа-яЁё]+)', r'<span class="text-rus">\1</span>', text)

@register.filter
def make_link(text):
    return re.sub(r'<i>(см\.|ср\.)</i>\s([A-Za-z’ÜüÄäÖöŠšČčŽži̮]+);?', r'<i>\1</i> <a href="/search/\2">\2</A>', text)

# @register.filter
# def make_link(word):
#     return word.split(',')[0]