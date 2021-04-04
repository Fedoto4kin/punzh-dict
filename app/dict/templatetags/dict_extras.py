from django import template
import re

register = template.Library()


@register.filter(name='nice')
def nice(text):
    # TODO: only in <b> tag and remove ||
    return text.replace('||', '<span class="text-muted font-weight-normal">||</span>') \
               .replace('|', '<span class="text-muted font-weight-normal">|</span>')


@register.filter(name='clear')
def clear(text):
    base = re.split(r'\|+', text.split(',')[0])[0]
    return text.replace('~', base.strip()) \
               .replace('|', '') \
               .replace('’', '')

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)