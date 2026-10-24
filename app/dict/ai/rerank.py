"""
LLM re-rank of AI search result tops.

Head (top N): full permutation only — no drops in the head.
Tail (after N): keep or drop as a whole via keep_tail.
Invalid LLM output → keep SQL order. No HTML in prompt.
"""

from __future__ import annotations

import logging

from django.conf import settings

from dict.ai import client as ai_client
from dict.ai.rank import SORT_ALPHA, normalize_sort
from dict.ai.rerank_prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT_RERANK,
    build_rerank_user_prompt,
)
from dict.models import ArticleIndexTag, ArticleIndexTranslate, ArticleSemanticField

logger = logging.getLogger(__name__)

RERANK_TOP_N = 30
RERANK_TIMEOUT = 25


def rerank_enabled():
    return bool(getattr(settings, "AI_SEARCH_LLM_RERANK", False))


def validate_order(expected_ids, order_raw, *, allow_drop=False):
    """
    Normalize order_raw to ids from expected_ids (no dupes, no unknowns).

    allow_drop=False: full permutation required.
    allow_drop=True: non-empty subset ok (then complete_head_order fills rest).
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
    if not got:
        return None
    return got


def validate_permutation(expected_ids, order_raw):
    return validate_order(expected_ids, order_raw, allow_drop=False)


def complete_head_order(expected_ids, order_prefix):
    """
    Prefix of head ids (validated subset) + remaining head ids in prior order.
    """
    expected = list(expected_ids)
    prefix = validate_order(expected, order_prefix, allow_drop=True)
    if prefix is None:
        return None
    seen = set(prefix)
    rest = [i for i in expected if i not in seen]
    return prefix + rest


def parse_keep_tail(raw, *, default=True):
    """Bool from LLM; missing/invalid → default (keep tail = safer)."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("true", "1", "yes", "да"):
            return True
        if s in ("false", "0", "no", "нет"):
            return False
    return default


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


def llm_rerank_head(
    query, candidates, *, tail_count=0, timeout=RERANK_TIMEOUT, model=None
):
    """
    Call LLM. Return {"order": [...], "keep_tail": bool} or None on failure.
    order is a full permutation of candidate ids.

    model overrides TIMEWEB_AI_MODEL_RERANK (comparison runs).
    """
    if not candidates:
        return {"order": [], "keep_tail": True}
    expected = [c["id"] for c in candidates]
    model = (
        model
        or getattr(settings, "TIMEWEB_AI_MODEL_RERANK", "")
        or getattr(settings, "TIMEWEB_AI_MODEL_QUERY", "")
    )
    if not model:
        return None
    data = ai_client.chat_json(
        SYSTEM_PROMPT_RERANK,
        build_rerank_user_prompt(query, candidates, tail_count=tail_count),
        model,
        timeout=timeout,
    )
    if not data or not isinstance(data, dict):
        logger.info("rerank: no JSON (prompt=%s)", PROMPT_VERSION)
        return None
    order = complete_head_order(expected, data.get("order"))
    if order is None:
        logger.info("rerank: invalid head order discarded")
        return None
    keep_tail = parse_keep_tail(data.get("keep_tail"), default=True)
    return {"order": order, "keep_tail": keep_tail}


def llm_reorder_ids(query, candidates, *, timeout=RERANK_TIMEOUT):
    """Backward-compatible: return ordered head ids or None."""
    result = llm_rerank_head(query, candidates, tail_count=0, timeout=timeout)
    if result is None:
        return None
    return result["order"]


def apply_rerank_to_groups(query, groups, *, sort="relevance"):
    """
    Permute main group's top RERANK_TOP_N; optionally drop the tail.
    Demote см./от after merge.
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
    result = llm_rerank_head(query, candidates, tail_count=len(tail))
    if result is None:
        return groups

    by_id = {a["id"]: a for a in head}
    reordered = [by_id[i] for i in result["order"] if i in by_id]
    if result.get("keep_tail", True):
        merged = reordered + tail
    else:
        merged = reordered
    demote_ids = g.get("demote_ids") or []
    merged = _demote_ids_to_end(merged, demote_ids)
    g["articles"] = merged
    g["total"] = len(merged)
    g["tail_dropped"] = not result.get("keep_tail", True) and bool(tail)
    return groups
