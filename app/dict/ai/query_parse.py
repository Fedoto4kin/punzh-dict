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

# Cheaper/slower Timeweb models need more headroom than YandexGPT-class.
PARSE_TIMEOUT = 30
# Output cap. Haiku spends part of this budget before the JSON, so 600
# came back empty (finish_reason=length). 2000 still stops a repeat loop.
PARSE_MAX_TOKENS = 2000
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

# Russian POS words → grammar Tag.tag (type 2 parents).
POS_LEMMA_TO_TAG = {
    "глагол": "v",
    "глаголы": "v",
    "существительное": "s",
    "существительные": "s",
    "имя существительное": "s",
    "прилагательное": "a",
    "прилагательные": "a",
    "имя прилагательное": "a",
    "наречие": "adv",
    "наречия": "adv",
    "союз": "conj",
    "союзы": "conj",
    "предлог": "prep",
    "предлоги": "prep",
    "послелог": "postp",
    "послелоги": "postp",
    "частица": "particl",
    "частицы": "particl",
    "местоимение": "pron",
    "местоимения": "pron",
    "междометие": "interj",
    "междометия": "interj",
    "числительное": "num",
    "числительные": "num",
    "имя числительное": "num",
}
KNOWN_GRAMMAR_TAGS = frozenset(POS_LEMMA_TO_TAG.values())

# Meta words for dialect-only queries («весьегонский говор») — not translations.
DIALECT_META_LEMMAS = frozenset(
    {
        "весьегонский",
        "весьегонские",
        "весьегонского",
        "весьегонском",
        "весьегонская",
        "весьегонскую",
        "говор",
        "говоры",
        "говора",
        "говоре",
        "диалект",
        "диалекты",
        "диалекта",
        "всг",
        "всг.",
        "параллель",
        "параллели",
        "лексические параллели",
    }
)


def _normalize_yo(text):
    return (text or "").translate(str.maketrans({"ё": "е"}))


def _lemma_matches_field_label(lemma, name, definition=""):
    """
    True if a theme lemma appears in the ontology field name (or definition).

    Used to refine LLM fields without a prompt change: «погода» →
    «Природа и погода», «животные» → «Животный мир» (stem prefix).
    """
    lem = _normalize_yo(lemma).strip().lower()
    if len(lem) < 3:
        return False
    blob = _normalize_yo(f"{name} {definition or ''}").lower()
    if lem in blob:
        return True
    # RU inflection: животные / животный share «животн»
    stem_len = 6 if len(lem) >= 6 else (5 if len(lem) >= 5 else 0)
    return bool(stem_len and lem[:stem_len] in blob)


def fields_matching_lemmas(lemmas, field_defs):
    """
    SemanticField names whose label/definition match any theme lemma.

    field_defs: {name: definition}. Order follows field_defs insertion order.
    """
    seeds = []
    seen = set()
    for raw in lemmas or []:
        lem = _normalize_yo(raw).strip()
        key = lem.lower()
        if lem and key not in seen:
            seen.add(key)
            seeds.append(lem)
    if not seeds or not field_defs:
        return []
    out = []
    for name, definition in field_defs.items():
        if any(_lemma_matches_field_label(lem, name, definition) for lem in seeds):
            out.append(name)
    return out


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
        "tags_soft": [],
        "place": None,
        "dialect": None,
        "dropped": [],
        "display": "",
        "axes_display": "",
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
            "tags_soft": [],
            "place": None,
            "dialect": None,
            "dropped": [],
            "display": display,
            "axes_display": display,
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
        "tags_soft": [],
        "place": None,
        "dialect": None,
        "dropped": [],
        "display": f"карельское «{query}» в индексе не найдено",
        "axes_display": f"карельское «{query}» в индексе не найдено",
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


def _display_label(key, names):
    """Human label from closed-list name map; fall back to raw key."""
    if not key:
        return key
    label = (names or {}).get(key) or ""
    return label.strip() or key


def _build_display(
    lexical,
    focus,
    fields,
    tags,
    place,
    dialect,
    dropped,
    tag_names=None,
    place_names=None,
    dialect_names=None,
    tags_soft=None,
):
    # focus is used for ranking only — not shown in display.
    # Tags/place/dialect: prefer dictionary names («verbum, глагол») over codes.
    # Hard tags (named in query) = filter; soft = ranking hint only.
    parts = []
    if lexical:
        parts.append(" · ".join(lexical))
    if fields:
        # User-facing: «темы», not internal «поля» (SemanticField).
        parts.append("темы: " + ", ".join(fields))
    if tags:
        labels = [_display_label(t, tag_names) for t in tags]
        parts.append("пометы: " + ", ".join(labels))
    if tags_soft:
        labels = [_display_label(t, tag_names) for t in tags_soft]
        parts.append("учли пометы: " + ", ".join(labels))
    if place:
        parts.append("место: " + _display_label(place, place_names))
    if dialect:
        parts.append("говор: " + _display_label(dialect, dialect_names))
    # Body only — UI label is «Что искали» (no leading «искали:»).
    body = "; ".join(parts) if parts else ""
    if dropped:
        dropped_s = "«" + "», «".join(dropped) + "»"
        body = (body + "; " if body else "") + f"{dropped_s} пропущено"
    return _clip_str(body, MAX_DISPLAY_LEN)


def _tag_alias_map(tag_rows):
    """Lowercased tag/name → canonical Tag.tag for types 2 and 3."""
    out = {}
    for row in tag_rows or []:
        if row.get("type") not in (2, 3):
            continue
        tag = row.get("tag") or ""
        if not tag:
            continue
        out[tag.lower()] = tag
        name = (row.get("name") or "").strip()
        if name:
            out[name.lower()] = tag
            # "verbum, глагол" / "adjectivum, имя прилагательное"
            if "," in name:
                gloss = name.split(",")[-1].strip().lower()
                if gloss:
                    out[gloss] = tag
                    if gloss.startswith("имя "):
                        out[gloss[4:].strip()] = tag
    for lemma, tag in POS_LEMMA_TO_TAG.items():
        out[lemma] = tag
    return out


def _promote_tag_lemmas(items, tags, alias_map, allowed_tag_set=None):
    """
    Closed-list tag / POS lemmas leave free axes. If the tag is allowed, add it
    to tags; otherwise drop the lemma (never leave POS in related).
    """
    kept = []
    allowed = allowed_tag_set
    for item in items:
        key = (item or "").strip().lower()
        canon = alias_map.get(key)
        if canon:
            if allowed is None or canon in allowed:
                if canon not in tags:
                    tags.append(canon)
            continue
        kept.append(item)
    return kept


def _narrow_grammar_tags(tags, query):
    """
    If the LLM piled several type-2 POS tags, keep only those named in the query
    (глагол→v). Stylistic tags (type 3) are untouched here.

    Grammar parents come from KNOWN_GRAMMAR_TAGS; DB type=2 covers the same
    and any extra grammar tags not in the POS alias map.
    """
    if not tags or not query:
        return tags
    from dict.models import Tag as TagModel

    type2 = {t for t in tags if t in KNOWN_GRAMMAR_TAGS}
    type2 |= set(
        TagModel.objects.filter(tag__in=tags, type=2).values_list("tag", flat=True)
    )
    if len(type2) <= 1:
        return tags
    q = query.lower()
    justified = set()
    for lemma, tag in POS_LEMMA_TO_TAG.items():
        if tag in type2 and lemma in q:
            justified.add(tag)
    if not justified:
        # Fall back: drop piled grammar tags (stylistic-only / mark-only query).
        return [t for t in tags if t not in type2]
    return [t for t in tags if t not in type2 or t in justified]


def _query_mentions_mark(needle, query):
    """True if mark label/code appears in the query (allow light inflection)."""
    needle = (needle or "").strip().lower().replace("ё", "е")
    q = (query or "").strip().lower().replace("ё", "е")
    if not needle or not q:
        return False
    if needle in q:
        return True
    stem = needle[:-1] if len(needle) > 4 else needle
    if len(stem) >= 4 and stem in q:
        return True
    compact_n = re.sub(r"[\s.]+", "", needle)
    compact_q = re.sub(r"[\s.]+", "", q)
    if len(compact_n) >= 3 and compact_n in compact_q:
        return True
    return False


def _partition_stylistic_tags(tags, query, tag_alias_map=None, tag_names=None):
    """
    Split type-3 tags into hard (named in query → AND filter) and soft
    (LLM inference → ranking boost only).

    Avoids AND-empty on invented marks («с.-х.» for «как варили пиво») while
    still letting inferred marks («бранн.» for «как ругаться») nudge order.
    Non-type-3 tags stay hard. No query → all hard (nothing to evidence).
    """
    if not tags:
        return [], []
    if not query:
        return list(tags), []
    from dict.models import Tag as TagModel

    type3 = set(
        TagModel.objects.filter(tag__in=tags, type=3).values_list("tag", flat=True)
    )
    if not type3:
        return list(tags), []

    alias_map = tag_alias_map or {}
    names = tag_names or {}
    aliases_for = {}
    for alias, canon in alias_map.items():
        aliases_for.setdefault(canon, []).append(alias)

    hard_type3 = set()
    for tag in type3:
        needles = [tag, names.get(tag) or ""]
        needles.extend(aliases_for.get(tag) or [])
        if any(_query_mentions_mark(n, query) for n in needles):
            hard_type3.add(tag)

    hard = [t for t in tags if t not in type3 or t in hard_type3]
    soft = [t for t in tags if t in type3 and t not in hard_type3]
    return hard, soft


def _normalize_parsed(
    data,
    field_defs,
    allowed_tags,
    allowed_dialects,
    allowed_places=None,
    tag_alias_map=None,
    tag_names=None,
    query="",
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
    alias_map = tag_alias_map or {}
    names_by_tag = tag_names or {}

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
        key = tag.strip().lower()
        canon = alias_map.get(key, tag)
        if canon in allowed_tag_set and canon not in tags:
            tags.append(canon)
        elif canon not in allowed_tag_set and tag not in allowed_tag_set:
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

    # Tag / POS lemmas must not stay in lexical/focus/related («рядом по теме»).
    lexical = _promote_tag_lemmas(lexical, tags, alias_map, allowed_tag_set)
    focus = _promote_tag_lemmas(focus, tags, alias_map, allowed_tag_set)
    related_raw = _promote_tag_lemmas(related_raw, tags, alias_map, allowed_tag_set)

    tags = _narrow_grammar_tags(tags, query)
    tags, tags_soft = _partition_stylistic_tags(
        tags, query, tag_alias_map=alias_map, tag_names=names_by_tag
    )

    # Mark / POS query: hard tags (AND), not semantic related/fields.
    # Drop speculative fields when grammar∩stylistic marks are both present.
    from dict.models import Tag as TagModel

    grammar_in_tags = any(t in KNOWN_GRAMMAR_TAGS for t in tags)
    tag_types = set(
        TagModel.objects.filter(tag__in=tags).values_list("type", flat=True)
    )
    if grammar_in_tags:
        tag_types.add(2)
    # Unit tests may lack Tag rows: non-grammar tags beside POS ≈ stylistic.
    if grammar_in_tags and any(t not in KNOWN_GRAMMAR_TAGS for t in tags):
        tag_types.add(3)
    # Pure mark/POS query → drop speculative fields. Keep fields when the
    # user also named a theme («про животных» → lexical/focus still set).
    if 2 in tag_types and 3 in tag_types and fields and not lexical and not focus:
        fields = []

    lex_lower = {x.lower() for x in lexical}
    focus_lower = {x.lower() for x in focus}
    # related must not duplicate lexical or focus
    related = [
        r
        for r in related_raw
        if r.lower() not in lex_lower and r.lower() not in focus_lower
    ]
    # Tags-primary (hard tags, no content lemmas): discard LLM «рядом по теме».
    if tags and not lexical and not focus:
        related = []
        fields = []

    place = _resolve_closed(data.get("place"), place_by_key, "place", warnings)
    dialect = _resolve_closed(data.get("dialect"), dialect_by_key, "dialect", warnings)

    # Dialect-only intent: drop meta lemmas from free axes (LLM often puts
    # «весьегонский» in lexical, which AND-filters всг. hits down to nothing).
    if dialect:

        def _not_dialect_meta(item):
            return (item or "").strip().lower() not in DIALECT_META_LEMMAS

        lexical = [x for x in lexical if _not_dialect_meta(x)]
        focus = [x for x in focus if _not_dialect_meta(x)]
        related = [x for x in related if _not_dialect_meta(x)]
        if not lexical and not focus:
            related = []
            fields = []

    # Internal theme refine (no prompt): lemmas that literally match a field
    # label win over speculative LLM fields («погода» ↛ «Животный мир»).
    matched_fields = fields_matching_lemmas(list(lexical) + list(focus), field_defs)
    if matched_fields:
        fields = matched_fields

    # LLM sometimes puts the same lemma in lexical AND dropped («один два три»
    # → три in both). Keep the axis; strip contradictions from dropped.
    kept_lower = (
        {x.lower() for x in lexical}
        | {x.lower() for x in focus}
        | {x.lower() for x in related}
    )
    dropped = [d for d in dropped if (d or "").strip().lower() not in kept_lower]

    raw_display = data.get("display") if isinstance(data.get("display"), str) else ""
    raw_display = raw_display.strip()
    if len(raw_display) > MAX_DISPLAY_LEN:
        warnings.append("display too long")
        raw_display = _clip_str(raw_display, MAX_DISPLAY_LEN)
    # Two UI lines: LLM prose («Как поняли») + validated axes («Что искали»).
    display = raw_display
    axes_display = _build_display(
        lexical,
        focus,
        fields,
        tags,
        place,
        dialect,
        dropped,
        tag_names=names_by_tag,
        place_names=allowed_places or {},
        dialect_names=allowed_dialects or {},
        tags_soft=tags_soft,
    )

    parse_ok = bool(lexical or focus or fields or tags or tags_soft or place or dialect)
    return {
        "lexical": lexical,
        "focus": focus,
        "related": related,
        "fields": fields,
        "tags": tags,
        "tags_soft": tags_soft,
        "tags_display": [_display_label(t, names_by_tag) for t in tags],
        "tags_soft_display": [_display_label(t, names_by_tag) for t in tags_soft],
        "place": place,
        "place_display": _display_label(place, allowed_places or {}),
        "dialect": dialect,
        "dialect_display": _display_label(dialect, allowed_dialects or {}),
        "dropped": dropped,
        "display": display,
        "axes_display": axes_display,
        "parse_ok": parse_ok,
        "krl_headword": False,
        "warnings": warnings,
        "raw": data,
    }


def parse_query(query, timeout=PARSE_TIMEOUT, model=None):
    """
    Parse one user query string. Returns a dict with ok, axes, parse_ok, warnings,
    raw, error, meta. ok=False only on LLM/infra failure; parse_ok=False means
    empty axes (caller should use lexical fallback).

    Latin/KRL headword queries that hit ArticleIndexWord skip the LLM
    (krl_headword=True); ä/a are NOT folded — kazi ≠ käzi.

    model overrides TIMEWEB_AI_MODEL_QUERY (comparison runs). None keeps
    the configured model.
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

    allowed_tags = [
        row["tag"] for row in tag_rows if row.get("type") in (2, 3) and row.get("tag")
    ]
    tag_names = {
        row["tag"]: row.get("name") or ""
        for row in tag_rows
        if row.get("type") in (2, 3) and row.get("tag")
    }
    allowed_dialects = {
        row["tag"]: row.get("name") or "" for row in tag_rows if row.get("type") == 4
    }
    allowed_places = {
        row["tag"]: row.get("name") or "" for row in tag_rows if row.get("type") == 1
    }
    tag_aliases = _tag_alias_map(tag_rows)
    model = model or getattr(settings, "TIMEWEB_AI_MODEL_QUERY", "")
    data = ai_client.chat_json(
        SYSTEM_PROMPT_QUERY_PARSE,
        build_query_parse_user_prompt(query, field_defs, tag_rows),
        model,
        timeout=timeout,
        max_tokens=PARSE_MAX_TOKENS,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    if data is None:
        return _empty_result(query, "llm_unavailable", latency_ms=latency_ms)

    payload = _normalize_parsed(
        data,
        field_defs,
        allowed_tags,
        allowed_dialects,
        allowed_places,
        tag_alias_map=tag_aliases,
        tag_names=tag_names,
        query=query,
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
