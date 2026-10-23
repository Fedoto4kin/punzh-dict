"""
Deterministic relevance ranking for AI search results.

No second LLM. Tiers prefer exact translation hits on `focus` (answer lemmas),
then exact lexical, then broader axis hits. Tie-break: Karelian alphabet.
"""

from __future__ import annotations

from dict.helpers import sorted_by_krl
from dict.models import Article, ArticleIndexTranslate, ArticleKeyword

SORT_RELEVANCE = "relevance"
SORT_ALPHA = "alpha"
SORT_MODES = (SORT_RELEVANCE, SORT_ALPHA)

# Score weights (higher = better).
# Translations (focus/lexical) first; ArticleKeyword illustrations are a weak
# second pass — they often hit example sentences (мальчик article mentions
# «девочка» in an illustration → must not outrank real «девочка» translations).
W_FOCUS_EXACT = 2000
W_FOCUS_SOFT = 900
W_LEX_EXACT = 80
W_LEX_HIT = 40
W_KW_FOCUS = 12
W_KW_LEX = 8
W_THEME_HIT = 15
W_TAG_HIT = 10
# Field contour: translation match inside field ≫ keyword/broader in field.
W_FIELD_TR = 55
W_FIELD_HIT = 5


def normalize_sort(raw):
    s = (raw or "").strip().lower()
    if s in SORT_MODES:
        return s
    return SORT_RELEVANCE


def _normalize_yo(text):
    return (text or "").translate(str.maketrans({"ё": "е"}))


def exact_translate_ids(lemmas):
    """Article ids with rus_word iexact any lemma (ё→е)."""
    if not lemmas:
        return set()
    q = None
    from django.db.models import Q

    for lem in lemmas:
        lem = _normalize_yo((lem or "").strip())
        if not lem:
            continue
        clause = Q(rus_word__iexact=lem)
        q = clause if q is None else (q | clause)
    if q is None:
        return set()
    return set(
        ArticleIndexTranslate.objects.filter(q).values_list("article_id", flat=True)
    )


def exact_keyword_ids(lemmas):
    if not lemmas:
        return set()
    from django.db.models import Q

    q = None
    for lem in lemmas:
        lem = (lem or "").strip()
        if not lem:
            continue
        clause = Q(word__iexact=lem)
        q = clause if q is None else (q | clause)
    if q is None:
        return set()
    return set(ArticleKeyword.objects.filter(q).values_list("article_id", flat=True))


def relevance_score(
    aid,
    *,
    focus_exact,
    focus_soft,
    lex_exact,
    kw_focus,
    kw_lex,
    lex_ids,
    theme_ids,
    tag_ids,
    field_pool,
    field_tr_ids=None,
):
    s = 0
    if aid in focus_exact:
        s += W_FOCUS_EXACT
    elif aid in focus_soft:
        s += W_FOCUS_SOFT
    if aid in lex_exact:
        s += W_LEX_EXACT
    if aid in kw_focus:
        s += W_KW_FOCUS
    if aid in kw_lex:
        s += W_KW_LEX
    if aid in lex_ids:
        s += W_LEX_HIT
    if aid in theme_ids:
        s += W_THEME_HIT
    if aid in tag_ids:
        s += W_TAG_HIT
    field_tr_ids = field_tr_ids or set()
    if aid in field_tr_ids:
        s += W_FIELD_TR
    elif aid in field_pool:
        s += W_FIELD_HIT
    return s


def order_articles(article_ids, score_fn, sort_mode=SORT_RELEVANCE):
    """
    Return [{id, word}, ...] and total.
    sort_mode=alpha → Karelian alphabet only; else score desc, then alpha.
    """
    if not article_ids:
        return [], 0
    rows = list(Article.objects.filter(id__in=article_ids).only("id", "word"))
    mode = normalize_sort(sort_mode)
    if mode == SORT_ALPHA:
        rows.sort(key=lambda a: (sorted_by_krl(a, "word"), a.id))
    else:
        rows.sort(key=lambda a: (-score_fn(a.id), sorted_by_krl(a, "word"), a.id))
    return [{"id": a.id, "word": a.word} for a in rows], len(rows)
