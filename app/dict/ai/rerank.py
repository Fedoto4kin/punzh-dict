"""
Soft LLM re-rank of AI search result tops.

Deterministic score builds the candidate pool; this module may gently
permute (and optionally drop clearly off-topic) the top N. Invalid LLM
output → keep SQL order. No HTML in prompt: id, word, all translations,
optional fields/tags.
"""

from __future__ import annotations

import logging
import math

from django.conf import settings

from dict.ai import client as ai_client
from dict.ai.rank import SORT_ALPHA, normalize_sort
from dict.ai.rerank_prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT_RERANK,
    build_rerank_user_prompt,
)
from dict.models import (
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleSemanticField,
)

logger = logging.getLogger(__name__)

RERANK_TOP_N = 30
RERANK_TIMEOUT = 12
# Keep at least this many, or half the pool (whichever is larger), after drops.
RERANK_MIN_KEEP = 8
RERANK_MIN_KEEP_RATIO = 0.5


def rerank_enabled():
    return bool(getattr(settings, "AI_SEARCH_LLM_RERANK", False))


def _min_keep(n_expected):
    if n_expected <= 0:
        return 0
    by_ratio = math.ceil(n_expected * RERANK_MIN_KEEP_RATIO)
    return max(1, min(n_expected, max(RERANK_MIN_KEEP, by_ratio)))


def validate_order(expected_ids, order_raw, *, allow_drop=True):
    """
    Normalize order_raw to a list of ids drawn from expected_ids (no dupes,
    no unknowns). Full permutation always ok. Subset ok when allow_drop and
    length >= min_keep. Else None.
    """
    if not isinstance(order_raw, list):
        return None
    expected = list(expected_ids)
    if not expected:
        return []
    try:
        got = [int(x) for x in order_raw]
    except (TypeError, ValueError):
        return None
    if len(got) != len(set(got)):
        return None
    expected_set = set(expected)
    if any(i not in expected_set for i in got):
        return None
    if not allow_drop:
        if len(got) != len(expected) or set(got) != expected_set:
            return None
        return got
    if len(got) < _min_keep(len(expected)):
        return None
    return got


# Backward-compatible alias used by tests.
def validate_permutation(expected_ids, order_raw):
    return validate_order(expected_ids, order_raw, allow_drop=False)


def _demote_ids_to_end(articles, demote_ids):
    if not demote_ids:
        return list(articles)
    demote = set(demote_ids)
    head = [a for a in articles if a.get("id") not in demote]
    tail = [a for a in articles if a.get("id") in demote]
    return head + tail


def _build_candidates(article_rows):
    """Load all translations + fields/tags for [{id, word}, ...]."""
    ids = [a["id"] for a in article_rows if a.get("id") is not None]
    if not ids:
        return []

    tr_map = {}
    for aid, rus in ArticleIndexTranslate.objects.filter(
        article_id__in=ids
    ).values_list("article_id", "rus_word"):
        tr_map.setdefault(aid, []).append(rus)

    field_map = {}
    for aid, name in (
        ArticleSemanticField.objects.filter(article_id__in=ids)
        .select_related("field")
        .values_list("article_id", "field__name")
    ):
        field_map.setdefault(aid, []).append(name)

    tag_map = {}
    for aid, tag in (
        ArticleIndexTag.objects.filter(article_id__in=ids)
        .select_related("tag")
        .values_list("article_id", "tag__tag")
    ):
        tag_map.setdefault(aid, []).append(tag)

    out = []
    for row in article_rows:
        aid = row["id"]
        out.append(
            {
                "id": aid,
                "word": row.get("word") or "",
                "translations": list(tr_map.get(aid) or []),
                "fields": list(field_map.get(aid) or []),
                "tags": list(tag_map.get(aid) or []),
            }
        )
    return out


def llm_reorder_ids(query, candidates, *, timeout=RERANK_TIMEOUT):
    """
    Call LLM; return ordered subset of candidate ids or None on failure.
    """
    if not candidates:
        return []
    expected = [c["id"] for c in candidates]
    model = getattr(settings, "TIMEWEB_AI_MODEL_RERANK", "") or getattr(
        settings, "TIMEWEB_AI_MODEL_QUERY", ""
    )
    if not model:
        return None
    data = ai_client.chat_json(
        SYSTEM_PROMPT_RERANK,
        build_rerank_user_prompt(query, candidates),
        model,
        timeout=timeout,
    )
    if not data or not isinstance(data, dict):
        logger.info("rerank: no JSON (prompt=%s)", PROMPT_VERSION)
        return None
    order = validate_order(expected, data.get("order"), allow_drop=True)
    if order is None:
        logger.info("rerank: invalid order discarded")
        return None
    return order


def apply_rerank_to_groups(query, groups, *, sort="relevance"):
    """
    Soft-reorder (and optionally trim) the main group's top RERANK_TOP_N.
    Dropped head ids are removed; tail after TOP_N stays. Demote см./от after.
    """
    mode = normalize_sort(sort)
    if mode == SORT_ALPHA or not rerank_enabled():
        return groups
    if not groups:
        return groups

    g = groups[0]
    articles = list(g.get("articles") or [])
    if len(articles) < 2:
        return groups

    head = articles[:RERANK_TOP_N]
    tail = articles[RERANK_TOP_N:]
    candidates = _build_candidates(head)
    order = llm_reorder_ids(query, candidates)
    if order is None:
        return groups

    by_id = {a["id"]: a for a in head}
    reordered = [by_id[i] for i in order if i in by_id]
    demote_ids = g.get("demote_ids") or []
    # Dropped from head are omitted (not appended). Tail unchanged.
    merged = _demote_ids_to_end(reordered + tail, demote_ids)
    g["articles"] = merged
    g["total"] = len(merged)
    return groups
