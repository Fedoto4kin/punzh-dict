"""
Staff browser for ArticleIndexTranslate: find articles by rus_word and
show headword + article HTML + full translation list.
"""

from dataclasses import dataclass, field
from typing import List, Set

from django.core.paginator import Paginator

from .helpers import canonical_rus_word, sorted_by_krl
from .models import Article, ArticleIndexTranslate

MODE_EXACT = "exact"
MODE_CONTAINS = "contains"
MODE_PREFIX = "prefix"
MODES = (MODE_EXACT, MODE_CONTAINS, MODE_PREFIX)

SORT_WORD = "word"
SORT_HIT = "hit"
SORTS = (SORT_WORD, SORT_HIT)

CARDS_PER_PAGE = 20


@dataclass
class TranslationCard:
    article: Article
    translations: List[str]
    hit_translations: Set[str] = field(default_factory=set)

    @property
    def sort_hit_key(self):
        if self.hit_translations:
            return min(t.lower() for t in self.hit_translations)
        return ""


def normalize_mode(mode):
    mode = (mode or MODE_EXACT).strip().lower()
    return mode if mode in MODES else MODE_EXACT


def normalize_sort(sort, mode):
    sort = (sort or "").strip().lower()
    if sort in SORTS:
        return sort
    # Exact hits share the same rus_word — default to headword order.
    if mode == MODE_EXACT:
        return SORT_WORD
    return SORT_HIT


def matching_translate_rows(query, mode=MODE_EXACT):
    """
    Queryset of ArticleIndexTranslate rows matching query under mode.
    Empty query → empty queryset. Query is canonicalized (ё→е, strip).
    """
    q = canonical_rus_word(query or "")
    if not q:
        return ArticleIndexTranslate.objects.none()

    mode = normalize_mode(mode)
    qs = ArticleIndexTranslate.objects.all()
    if mode == MODE_EXACT:
        return qs.filter(rus_word__iexact=q)
    if mode == MODE_PREFIX:
        return qs.filter(rus_word__istartswith=q)
    return qs.filter(rus_word__icontains=q)


def build_translation_cards(query, mode=MODE_EXACT, sort=None):
    """
    Articles that have at least one matching rus_word, each with full
    translation list and the subset that matched the query.
    """
    mode = normalize_mode(mode)
    sort = normalize_sort(sort, mode)
    rows = matching_translate_rows(query, mode)
    if not rows.exists():
        return []

    hits_by_article = {}
    for aid, rus_word in rows.values_list("article_id", "rus_word"):
        if rus_word:
            hits_by_article.setdefault(aid, set()).add(rus_word)

    article_ids = list(hits_by_article.keys())
    articles = {
        a.pk: a
        for a in Article.objects.filter(pk__in=article_ids).select_related("source")
    }

    all_by_article = {}
    for aid, rus_word in (
        ArticleIndexTranslate.objects.filter(article_id__in=article_ids)
        .order_by("rus_word")
        .values_list("article_id", "rus_word")
    ):
        if rus_word:
            all_by_article.setdefault(aid, []).append(rus_word)

    cards = []
    for aid, hits in hits_by_article.items():
        article = articles.get(aid)
        if article is None:
            continue
        translations = all_by_article.get(aid, [])
        # Hits first (alpha), then the rest (alpha) — stable within card.
        hit_list = sorted(
            (t for t in translations if t in hits), key=lambda t: t.lower()
        )
        rest = [t for t in translations if t not in hits]
        cards.append(
            TranslationCard(
                article=article,
                translations=hit_list + rest,
                hit_translations=hits,
            )
        )

    if sort == SORT_HIT:
        cards.sort(
            key=lambda c: (
                c.sort_hit_key,
                sorted_by_krl(c.article, "word"),
                c.article.pk,
            )
        )
    else:
        cards.sort(key=lambda c: (sorted_by_krl(c.article, "word"), c.article.pk))

    return cards


def paginate_cards(cards, page=1, per_page=CARDS_PER_PAGE):
    paginator = Paginator(cards, per_page)
    return paginator.get_page(page)
