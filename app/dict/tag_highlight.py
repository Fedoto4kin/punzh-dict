"""Highlight dictionary tags (пометы) in article HTML without per-card Tag queries."""

import re
import threading
from functools import lru_cache

# Types 1–4 appear as <i>{tag}</i> (same needles as reindex_tags). Type 5 is bare
# text (currently only ◊) and is skipped to avoid false positives.
_ITALIC_TAG_TYPES = (1, 2, 3, 4)

_local = threading.local()
_ITALIC_RE = re.compile(r"<i>([^<]*)</i>")


@lru_cache(maxsize=1)
def _load_italic_tag_values():
    from dict.models import Tag

    return frozenset(
        Tag.objects.filter(type__in=_ITALIC_TAG_TYPES)
        .exclude(tag="")
        .exclude(tag__isnull=True)
        .values_list("tag", flat=True)
    )


def get_italic_tag_values():
    """
    Tag.tag values for types 1–4.

    Thread-local + process cache: one Tag query per request (or until clear),
    then reuse for every article card on the page.
    """
    cached = getattr(_local, "italic_tags", None)
    if cached is not None:
        return cached
    values = _load_italic_tag_values()
    _local.italic_tags = values
    return values


def clear_italic_tag_cache():
    _local.italic_tags = None
    _load_italic_tag_values.cache_clear()


def highlight_tags(html):
    """Wrap known Tag values in <i class=\"text-tag\">…</i>. Leaves other <i> alone."""
    if not html:
        return html or ""
    values = get_italic_tag_values()
    if not values:
        return html

    def repl(match):
        inner = match.group(1)
        if inner in values:
            return f'<i class="text-tag">{inner}</i>'
        return match.group(0)

    return _ITALIC_RE.sub(repl, html)


def format_article_html(html):
    """Public/admin display pipeline for article_html."""
    from dict.templatetags.dict_extras import (
        highlight_rus,
        make_break,
        make_link,
        nice,
    )

    if not html:
        return ""
    return highlight_rus(highlight_tags(make_break(nice(make_link(html)))))
