"""Shared search primitives: Content, pagination, links, direction."""

import re
from dataclasses import dataclass

from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q

from dict.helpers import build_pagination_hints, normalization, sorted_by_krl
from dict.models import Article, ArticleAddition, ArticleLink

num_by_page = 18


@dataclass
class Content:
    """Container returned by the listing/search views."""

    page_obj: object = None
    last_page_word: str = ""
    first_page_word: str = ""
    trigrams_dict: object = None
    tag_filter_groups: object = None
    phrase_filter: object = None
    t_query: str = ""


# ------------------------------------------------------------
#  Общий примитив: карельская сортировка + пагинация
# ------------------------------------------------------------


def _hydrate_article_page(page_obj):
    """
    Replace light Article rows on the current page with full cards
    (html, source, additions) for templates.
    """
    page_ids = [a.pk for a in page_obj.object_list]
    if not page_ids:
        return page_obj
    additions_qs = ArticleAddition.objects.select_related("source")
    full_by_id = {
        a.pk: a
        for a in Article.objects.filter(pk__in=page_ids)
        .select_related("source")
        .prefetch_related(Prefetch("additions", queryset=additions_qs))
    }
    page_obj.object_list = [full_by_id[i] for i in page_ids if i in full_by_id]
    return page_obj


def sort_and_paginate(articles, page):
    """
    Karelian-collated in-memory sort + pagination, shared by every listing
    view. `articles` is a filtered Article queryset (or any iterable).

    Sorting must run in Python: sorted_by_krl relies on normalization(),
    which is regex-based and cannot be expressed in SQL. Only id/word are
    loaded for the sort; the current page is re-fetched with source and
    additions for card templates.

    Returns (page_obj, sorted_articles); the sorted list is reused by callers
    for build_pagination_hints (word only).
    """
    if hasattr(articles, "only"):
        articles = articles.only("id", "word")
    sorted_articles = sorted(articles, key=lambda el: sorted_by_krl(el, "word"))
    paginator = Paginator(sorted_articles, num_by_page)
    page_obj = _hydrate_article_page(paginator.get_page(page))
    return page_obj, sorted_articles


# ------------------------------------------------------------
#  Расширение списка статей через связи ArticleLink
# ------------------------------------------------------------


def expand_by_links(article_ids, *, sides="both"):
    """
    One-hop cluster by ArticleLink (см. and от; never ср.).

    sides:
      "both" — classical /search/: follow outgoing and incoming
      "incoming" — AI search: only articles that say см./от *to* a hit
                  (not targets of см./от *from* a hit)
    """
    seed = set(article_ids)
    if not seed:
        return set()
    kinds = ArticleLink.KINDS_LISTING
    extra = set()
    if sides in ("both", "outgoing"):
        extra |= set(
            ArticleLink.objects.filter(
                from_article_id__in=seed, kind__in=kinds
            ).values_list("to_article_id", flat=True)
        )
    if sides in ("both", "incoming"):
        extra |= set(
            ArticleLink.objects.filter(
                to_article_id__in=seed, kind__in=kinds
            ).values_list("from_article_id", flat=True)
        )
    return seed | extra


# ------------------------------------------------------------
#  Поиск по букве
# ------------------------------------------------------------


def search_by_pointer(letter: str, page: int) -> Content:

    articles = Article.objects.filter(first_letter=letter.upper())
    page_obj, sorted_articles = sort_and_paginate(articles, page)

    trigrams_dict = build_pagination_hints(sorted_articles, num_by_page)

    last_page_word = ""
    first_page_word = ""
    if len(page_obj):
        last_page_word = normalization(page_obj[-1].word)
        first_page_word = normalization(page_obj[0].word)

    return Content(
        page_obj=page_obj,
        last_page_word=last_page_word,
        first_page_word=first_page_word,
        trigrams_dict=trigrams_dict,
    )


# ------------------------------------------------------------
#  Общий метод сортировки + пагинации
# ------------------------------------------------------------


def get_sorted_articles(ids: [], page: int) -> Paginator:
    articles = Article.objects.filter(pk__in=ids)
    page_obj, _ = sort_and_paginate(articles, page)

    return page_obj, page_obj.paginator.count


# ------------------------------------------------------------
#  Определение направления поиска в словаре
# ------------------------------------------------------------


def detect_direction(query: str) -> str:
    """
    Decide the search direction from the query text.

    A query is Russian ('rus') if it contains any Cyrillic letter; otherwise
    it is Karelian ('krl'), which is written in Latin script with diacritics.
    Cyrillic presence anywhere is the signal — not the first character, and
    punctuation/whitespace (including the '.'/'?' fuzzy-search syntax) never
    affects the choice.
    """
    if re.search(r"[а-яё]", query, re.IGNORECASE):
        return "rus"
    return "krl"
