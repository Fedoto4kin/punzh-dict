"""
Parse a natural-language Russian search query into search axes (lexical, fields, tags).

Uses TIMEWEB_AI_MODEL_QUERY via dict.ai.client. Never raises — returns ok=False
on LLM/parse failure so callers can fall back to lexical /search/.

Latin-only queries that hit the Karelian word index skip the LLM: models often
map lookalikes via Finnish/Karelian cognates (kazi → käzi «рука») and invent
wrong fields/related.
"""

import logging
import re
import time

from django.conf import settings

from dict.ai import client as ai_client
from dict.ai.query_prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT_QUERY_PARSE,
    build_query_parse_user_prompt,
    reference_data_for_parse,
)

logger = logging.getLogger(__name__)

PARSE_TIMEOUT = 15
MAX_QUERY_LEN = 300
MAX_LIST_ITEMS = 10
MAX_RELATED_ITEMS = 12
MAX_FOCUS_ITEMS = 5
MAX_ITEM_LEN = 80
MAX_DISPLAY_LEN = 200
MAX_KRL_QUERY_LEN = 40

# Cyrillic → treat as Russian NL (LLM path).
_CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")
# Latin + Karelian orthography letters / apostrophes.
_KRL_SCRIPT_RE = re.compile(r"[a-zA-ZäöüÄÖÜčšžČŠŽ’'ʼ]")


def looks_like_krl_query(query):
    """
    True when the string looks like a Karelian headword typed in dictionary
    orthography (Latin), not a Russian NL request.
    """
    q = (query or "").strip()
    if not q or len(q) > MAX_KRL_QUERY_LEN:
        return False
    if _CYRILLIC_RE.search(q):
        return False
    if not _KRL_SCRIPT_RE.search(q):
        return False
    # Reject obvious multi-sentence / English glue; allow 1–3 tokens.
    if len(q.split()) > 3:
        return False
    return True


def _base_meta(latency_ms=0, model=None, path=None):
    meta = {
        "model": (
            model
            if model is not None
            else getattr(settings, "TIMEWEB_AI_MODEL_QUERY", "")
        ),
        "prompt_version": PROMPT_VERSION,
        "latency_ms": latency_ms,
    }
    if path:
        meta["path"] = path
    return meta


def _empty_result(query, error, latency_ms=0):
    return {
        "ok": False,
        "query": query,
        "lexical": [],
        "focus": [],
        "related": [],
        "fields": [],
        "tags": [],
        "place": None,
        "dialect": None,
        "dropped": [],
        "display": "",
        "parse_ok": False,
        "krl_headword": False,
        "warnings": [],
        "raw": None,
        "error": error,
        "meta": _base_meta(latency_ms),
    }


def _krl_headword_result(query, found, latency_ms=0):
    """Bypass LLM for Latin/KRL headword queries (see module docstring)."""
    if found:
        display = f"искали карельское слово «{query}»"
        return {
            "ok": True,
            "query": query,
            "lexical": [],
            "focus": [],
            "related": [],
            "fields": [],
            "tags": [],
            "place": None,
            "dialect": None,
            "dropped": [],
            "display": display,
            "parse_ok": True,
            "krl_headword": True,
            "warnings": [],
            "raw": None,
            "error": None,
            "meta": _base_meta(latency_ms, model="", path="krl_headword"),
        }
    return {
        "ok": True,
        "query": query,
        "lexical": [],
        "focus": [],
        "related": [],
        "fields": [],
        "tags": [],
        "place": None,
        "dialect": None,
        "dropped": [],
        "display": f"карельское «{query}» в индексе не найдено",
        "parse_ok": False,
        "krl_headword": False,
        "warnings": ["krl_headword_miss"],
        "raw": None,
        "error": None,
        "meta": _base_meta(latency_ms, model="", path="krl_headword_miss"),
    }


def _clip_str(value, max_len):
    if not isinstance(value, str):
        return ""
    s = value.strip()
    if len(s) > max_len:
        return s[:max_len].rstrip()
    return s


def _as_str_list(raw, max_items=MAX_LIST_ITEMS, max_item_len=MAX_ITEM_LEN):
    if not isinstance(raw, list):
        return [], 0
    out = []
    truncated = 0
    for item in raw:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if not s:
            continue
        if len(s) > max_item_len:
            s = s[:max_item_len].rstrip()
            truncated += 1
        if s and s not in out:
            out.append(s)
        if len(out) >= max_items:
            break
    return out, truncated


def _closed_lookup(mapping):
    """tag/name (lower) → canonical tag."""
    by_key = {}
    for tag, name in mapping.items():
        by_key[tag.lower()] = tag
        if name:
            by_key[name.lower()] = tag
    return by_key


def _resolve_closed(raw, by_key, kind, warnings):
    if not isinstance(raw, str) or not raw.strip():
        return None
    key = raw.strip().lower()
    if key in by_key:
        return by_key[key]
    warnings.append(f"unknown {kind}: {raw.strip()}")
    return None


def _build_display(lexical, focus, fields, tags, place, dialect, dropped):
    parts = []
    if focus:
        parts.append("ответ: " + " · ".join(focus))
    if lexical:
        parts.append(" · ".join(lexical))
    if fields:
        parts.append("поля: " + ", ".join(fields))
    if tags:
        parts.append("пометы: " + ", ".join(tags))
    if place:
        parts.append("место: " + place)
    if dialect:
        parts.append("говор: " + dialect)
    display = "искали: " + "; ".join(parts) if parts else ""
    if dropped:
        dropped_s = "«" + "», «".join(dropped) + "»"
        display = (display + "; " if display else "") + f"{dropped_s} пропущено"
    return _clip_str(display, MAX_DISPLAY_LEN)


def _normalize_parsed(
    data, field_defs, allowed_tags, allowed_dialects, allowed_places=None
):
    """
    Validate LLM JSON against closed lists. Returns payload dict
    (keys match public parse_query result without ok/meta/error).
    """
    warnings = []
    allowed_fields = set(field_defs)
    allowed_tag_set = set(allowed_tags)
    dialect_by_key = _closed_lookup(allowed_dialects)
    place_by_key = _closed_lookup(allowed_places or {})

    raw_fields, _ = _as_str_list(data.get("fields"))
    fields = []
    for name in raw_fields:
        if name in allowed_fields and name not in fields:
            fields.append(name)
        elif name not in allowed_fields:
            warnings.append(f"unknown field: {name}")

    raw_tags, _ = _as_str_list(data.get("tags"))
    tags = []
    for tag in raw_tags:
        if tag in allowed_tag_set and tag not in tags:
            tags.append(tag)
        elif tag not in allowed_tag_set:
            warnings.append(f"unknown tag: {tag}")

    lexical, lex_trunc = _as_str_list(data.get("lexical"))
    focus, focus_trunc = _as_str_list(data.get("focus"), max_items=MAX_FOCUS_ITEMS)
    related_raw, rel_trunc = _as_str_list(
        data.get("related"), max_items=MAX_RELATED_ITEMS
    )
    dropped, drop_trunc = _as_str_list(data.get("dropped"))
    if lex_trunc:
        warnings.append("lexical items truncated")
    if focus_trunc:
        warnings.append("focus items truncated")
    if rel_trunc:
        warnings.append("related items truncated")
    if drop_trunc:
        warnings.append("dropped items truncated")

    lex_lower = {x.lower() for x in lexical}
    focus_lower = {x.lower() for x in focus}
    # related must not duplicate lexical or focus
    related = [
        r
        for r in related_raw
        if r.lower() not in lex_lower and r.lower() not in focus_lower
    ]

    place = _resolve_closed(data.get("place"), place_by_key, "place", warnings)
    dialect = _resolve_closed(data.get("dialect"), dialect_by_key, "dialect", warnings)

    display_raw = data.get("display")
    display = ""
    if isinstance(display_raw, str):
        display = display_raw.strip()
        if len(display) > MAX_DISPLAY_LEN:
            warnings.append("display too long; rebuilt from axes")
            display = ""
    if not display:
        display = _build_display(lexical, focus, fields, tags, place, dialect, dropped)
    else:
        display = _clip_str(display, MAX_DISPLAY_LEN)

    parse_ok = bool(lexical or focus or fields or tags or place or dialect)
    return {
        "lexical": lexical,
        "focus": focus,
        "related": related,
        "fields": fields,
        "tags": tags,
        "place": place,
        "dialect": dialect,
        "dropped": dropped,
        "display": display,
        "parse_ok": parse_ok,
        "krl_headword": False,
        "warnings": warnings,
        "raw": data,
    }


def parse_query(query, timeout=PARSE_TIMEOUT):
    """
    Parse one user query string. Returns a dict with ok, axes, parse_ok, warnings,
    raw, error, meta. ok=False only on LLM/infra failure; parse_ok=False means
    empty axes (caller should use lexical fallback).

    Latin/KRL headword queries that hit ArticleIndexWord skip the LLM
    (krl_headword=True); ä/a are NOT folded — kazi ≠ käzi.
    """
    query = (query or "").strip()
    if not query:
        return _empty_result(query, "empty_query")

    truncated_input = False
    if len(query) > MAX_QUERY_LEN:
        query = query[:MAX_QUERY_LEN].rstrip()
        truncated_input = True

    t0 = time.monotonic()

    if looks_like_krl_query(query):
        from dict.search import krl_article_ids

        found = krl_article_ids(query).exists()
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _krl_headword_result(query, found, latency_ms=latency_ms)

    field_defs, tag_rows = reference_data_for_parse()
    if not field_defs:
        return _empty_result(query, "empty_ontology", latency_ms=0)

    allowed_tags = [row["tag"] for row in tag_rows if row.get("type") == 3]
    allowed_dialects = {
        row["tag"]: row.get("name") or "" for row in tag_rows if row.get("type") == 4
    }
    allowed_places = {
        row["tag"]: row.get("name") or "" for row in tag_rows if row.get("type") == 1
    }
    model = getattr(settings, "TIMEWEB_AI_MODEL_QUERY", "")
    data = ai_client.chat_json(
        SYSTEM_PROMPT_QUERY_PARSE,
        build_query_parse_user_prompt(query, field_defs, tag_rows),
        model,
        timeout=timeout,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    if data is None:
        return _empty_result(query, "llm_unavailable", latency_ms=latency_ms)

    payload = _normalize_parsed(
        data, field_defs, allowed_tags, allowed_dialects, allowed_places
    )
    if truncated_input:
        payload["warnings"] = list(payload["warnings"]) + ["query truncated"]
    return {
        "ok": True,
        "query": query,
        "error": None,
        "meta": _base_meta(latency_ms, model=model),
        **payload,
    }
