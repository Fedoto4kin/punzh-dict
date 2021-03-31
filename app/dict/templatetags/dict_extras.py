from django import template

register = template.Library()

@register.filter(name='nice')
def nice(text):
    # TODO: only in <b> tag
    return text.replace('||', '') \
               .replace('|', '<span class="text-muted font-weight-normal">|</span>')

# TODO: replace ~ with word