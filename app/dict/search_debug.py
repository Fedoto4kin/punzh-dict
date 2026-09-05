"""
Staff explain for the Russian lexical search pipeline.
Reuses rus_search_core — no second copy of match logic.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from django.db.models import Q

from .models import Article, ArticleLink
from .search import (
    _FUZZY_TOKEN_MIN_LEN,
    _token_boundary_fuzzy_regex,
    _token_boundary_regex,
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
    fuzzy: bool = False
    inherited: bool = False
    via: List[dict] = field(default_factory=list)  # {word, kind_label}

    @property
    def label(self):
        base = REASON_LABELS.get(self.code, self.code)
        if self.code == "token" and self.fuzzy:
            return base + "≈"
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
    table = str.maketrans({"ё": "е", "?": "%", ".": "_"})
    return (raw_query or "").strip().translate(table)


def _token_match_info(rus_words, query_tokens):
    """
    Among rus_words, which phrases match any query token as a whole word,
    and whether any match needed the fuzzy one-letter suffix.
    """
    matched = []
    any_fuzzy = False
    for rw in rus_words:
        if not rw:
            continue
        exact_hit = False
        fuzzy_hit = False
        for tok in query_tokens:
            if re.search(_token_boundary_regex(tok), rw, flags=re.IGNORECASE):
                exact_hit = True
                break
            if len(tok) >= _FUZZY_TOKEN_MIN_LEN and re.search(
                _token_boundary_fuzzy_regex(tok), rw, flags=re.IGNORECASE
            ):
                fuzzy_hit = True
        if exact_hit or fuzzy_hit:
            matched.append(rw)
            if fuzzy_hit and not exact_hit:
                any_fuzzy = True
    return matched, any_fuzzy


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
        matched, fuzzy = _token_match_info(translations, core.query_tokens)
        reasons.append(
            DebugReason(
                code="token",
                detail=(
                    "слово запроса целиком в фразе перевода"
                    + (" (одна буква на конце)" if fuzzy else "")
                ),
                matched=matched,
                fuzzy=fuzzy,
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
