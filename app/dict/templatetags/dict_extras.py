import re
from django import template

register = template.Library()


@register.filter
def nice(text):
    # TODO: only in <b> tags
    return re.sub(r'([\|]{1,2})', r'<span class="text-muted font-weight-normal">\1</span>', text)


@register.filter
def clear(text):
    base = re.split(r'\|+', text.split(',')[0])[0] # TODO: rewrite with re.sub or re.find
    return text.replace('~', base.strip()) \
               .replace('|', '') \
               .replace('’', '')


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def highlight_rus(text):
    return re.sub(r'([А-яЁё]+)', r'<span class="text-rus">\1</span>', text)
