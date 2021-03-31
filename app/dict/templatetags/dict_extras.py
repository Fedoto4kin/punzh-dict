from django import template

register = template.Library()

@register.filter(name='nice')
def nice(text):
    # TODO: only in <b> tag and remove ||
    return text.replace('||', '<span class="text-muted font-weight-normal">||</span>') \
               .replace('|', '<span class="text-muted font-weight-normal">|</span>')

# TODO: replace ~ with word