"""
Staff explain for the Russian lexical search pipeline.
Reuses rus_search_core — no second copy of match logic.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set

from django.db.models import Q

from .helpers import (
    lemma_token,
    lemmas_of_phrase,
    prepare_rus_query,
    query_tokens,
)
from .models import Article, ArticleLink
from .search import (
    get_sorted_articles,
    rus_search_core,
)


REASON_LABELS = {
    "ilike": "равенство",
    "token": "слово в фразе",
    "link": "связь",
    "exact": "точные",
}


@dataclass
class DebugReason:
    code: str  # ilike | token | link | exact
    detail: str = ""
    matched: List[str] = field(default_factory=list)
    lemma: bool = False
    inherited: bool = False
    via: List[dict] = field(default_factory=list)  # {word, kind_label}

    @property
    def fuzzy(self):
        # Compat for templates/tests that still read .fuzzy (P3: lemma match).
        return self.lemma

    @property
    def label(self):
        base = REASON_LABELS.get(self.code, self.code)
        if self.code == "token" and self.lemma:
            return base + "≅"
        if self.code == "exact" and self.inherited:
            return base + "↓"
        return base


@dataclass
class DebugCard:
    article: Article
    translations: List[str]
    reasons: List[DebugReason]
    in_exact: bool
    in_filtered: bool

    @property
    def matched_translations(self):
        out = set()
        for r in self.reasons:
            out.update(r.matched)
        return out


@dataclass
class SearchDebugResult:
    raw_query: str
    query: str
    query_tokens: List[str]
    query_lemmas: List[str]
    high_freq_anchor: bool
    f: Optional[str]
    counts: dict
    narrowing: list
    related_queries: list
    direct_ids: Set[int]
    page_obj: object
    found_count: int
    cards: List[DebugCard]


def prepare_rus_debug_query(raw_query: str) -> str:
    """Same prep as views.search for the Russian branch (ё→е, ?/. wildcards)."""
    return prepare_rus_query(raw_query)


def _token_match_info(rus_words, query_lemma_list):
    """
    Phrases whose token lemmas overlap query lemmas.
    `by_lemma` is True when at least one hit uses an inflected surface
    (surface token ≠ its lemma), not a bare dictionary-form equality.
    """
    q_lemmas = {lem for lem in (query_lemma_list or []) if lem}
    matched = []
    by_lemma = False
    for rw in rus_words:
        if not rw:
            continue
        if not (set(lemmas_of_phrase(rw)) & q_lemmas):
            continue
        matched.append(rw)
        for tok in query_tokens(rw):
            lem = lemma_token(tok)
            if lem in q_lemmas and tok != lem:
                by_lemma = True
                break
    return matched, by_lemma


def _link_via(aid, seed_ids, articles_by_id):
    """Neighbors in the seed set connected by см./от."""
    kind_labels = dict(ArticleLink.KIND_CHOICES)
    via = []
    seen = set()
    q = Q(
        from_article_id=aid,
        to_article_id__in=seed_ids,
        kind__in=ArticleLink.KINDS_LISTING,
    ) | Q(
        to_article_id=aid,
        from_article_id__in=seed_ids,
        kind__in=ArticleLink.KINDS_LISTING,
    )
    for fa, ta, kind in ArticleLink.objects.filter(q).values_list(
        "from_article_id", "to_article_id", "kind"
    ):
        other = ta if fa == aid else fa
        if other in seen:
            continue
        seen.add(other)
        other_art = articles_by_id.get(other)
        via.append(
            {
                "word": other_art.word if other_art else str(other),
                "kind_label": kind_labels.get(kind, kind),
                "article_id": other,
            }
        )
    via.sort(key=lambda row: row["word"])
    return via


def _build_reasons(aid, core, articles_by_id):
    reasons = []
    translations = core.blobs_by_article.get(aid, [])

    if aid in core.ids_ilike:
        matched = [rw for rw in translations if rw and rw.lower() == core.query.lower()]
        reasons.append(
            DebugReason(
                code="ilike",
                detail="перевод точно равен запросу",
                matched=matched or [core.query],
            )
        )

    if aid in core.token_match_ids:
        matched, by_lemma = _token_match_info(translations, core.query_lemmas)
        reasons.append(
            DebugReason(
                code="token",
                detail=(
                    "лемма слова запроса в фразе перевода"
                    if by_lemma
                    else "слово запроса целиком в фразе перевода"
                ),
                matched=matched,
                lemma=by_lemma,
            )
        )

    if aid in core.result_ids and aid not in core.seed_ids:
        via = _link_via(aid, core.seed_ids, articles_by_id)
        reasons.append(
            DebugReason(
                code="link",
                detail="только через см./от",
                via=via,
            )
        )

    if aid in core.direct_ids:
        inherited = aid not in core.ids_ilike
        reasons.append(
            DebugReason(
                code="exact",
                detail=(
                    "наследование см./от"
                    if inherited
                    else "точное равенство → фильтр «точные»"
                ),
                inherited=inherited,
            )
        )

    return reasons


def explain_rus_search(raw_query: str, f=None, page=1) -> SearchDebugResult:
    query = prepare_rus_debug_query(raw_query)
    if not query:
        return SearchDebugResult(
            raw_query=raw_query or "",
            query="",
            query_tokens=[],
            query_lemmas=[],
            high_freq_anchor=False,
            f=f,
            counts={},
            narrowing=[],
            related_queries=[],
            direct_ids=set(),
            page_obj=None,
            found_count=0,
            cards=[],
        )

    core = rus_search_core(query, f=f)
    page_obj, found_count = get_sorted_articles(core.filtered_ids, page)

    all_ids = set(core.result_ids) | set(core.filtered_ids)
    articles_by_id = {
        a.pk: a for a in Article.objects.filter(pk__in=all_ids).select_related("source")
    }

    cards = []
    for article in page_obj.object_list:
        aid = article.pk
        translations = sorted(
            core.blobs_by_article.get(aid, []), key=lambda t: t.lower()
        )
        cards.append(
            DebugCard(
                article=article,
                translations=translations,
                reasons=_build_reasons(aid, core, articles_by_id),
                in_exact=aid in core.direct_ids,
                in_filtered=aid in core.filtered_ids,
            )
        )

    counts = {
        "ilike": len(core.ids_ilike),
        "token": len(core.token_match_ids),
        "seed": len(core.seed_ids),
        "expanded": len(core.expanded_ids),
        "result": len(core.result_ids),
        "exact": len(core.direct_ids),
        "filtered": len(core.filtered_ids),
    }

    return SearchDebugResult(
        raw_query=raw_query or "",
        query=query,
        query_tokens=core.query_tokens,
        query_lemmas=core.query_lemmas,
        high_freq_anchor=core.high_freq_anchor,
        f=f,
        counts=counts,
        narrowing=core.narrowing,
        related_queries=core.related_queries,
        direct_ids=core.direct_ids,
        page_obj=page_obj,
        found_count=found_count,
        cards=cards,
    )
