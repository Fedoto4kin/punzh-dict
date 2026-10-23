"""
Deterministic retrieval for AI search: axes from parse_query → result groups.

No second LLM call. Reuses dict.search primitives (rus_search_core,
article_ids_for_semantic_field, ArticleIndexTag).
"""

from __future__ import annotations

from django.db.models import Prefetch, Q

from dict.models import (
    Article,
    ArticleAddition,
    ArticleIndexTag,
    ArticleKeyword,
    SemanticField,
    Tag,
)
from dict.ai.rank import (
    SORT_RELEVANCE,
    exact_keyword_ids,
    exact_translate_ids,
    normalize_sort,
    order_articles,
    relevance_score,
)
from dict.search import article_ids_for_semantic_field, krl_article_ids, rus_search_core

# Debug beta: show every card (no «ещё N» collapse). Kept as aliases for tests.
TOP_N = None  # None = unlimited
FIELD_TOP_N = None
KIND_ORDER = ("lexical", "tag")  # field merged into lexical/main


def _normalize_yo(text):
    return (text or "").translate(str.maketrans({"ё": "е"}))


def _lemma_hit_ids(lemmas):
    """Articles matching any lemma via translation index (ILIKE/token OR)."""
    if not lemmas:
        return set()
    query = _normalize_yo(" ".join(lemmas))
    core = rus_search_core(query)
    return set(core.result_ids or ())


def _keyword_hit_ids(lemmas):
    """Articles whose ArticleKeyword matches any lemma (exact, case-insensitive)."""
    if not lemmas:
        return set()
    q = Q()
    for lem in lemmas:
        lem = (lem or "").strip()
        if lem:
            q |= Q(word__iexact=lem)
    if not q:
        return set()
    return set(ArticleKeyword.objects.filter(q).values_list("article_id", flat=True))


def _theme_ids(lemmas):
    """Union of translation + keyword hits for thematic seeds."""
    return _lemma_hit_ids(lemmas) | _keyword_hit_ids(lemmas)


def _tag_ids(tag_strings):
    if not tag_strings:
        return set()
    tag_pks = list(Tag.objects.filter(tag__in=tag_strings).values_list("id", flat=True))
    if not tag_pks:
        return set()
    return set(
        ArticleIndexTag.objects.filter(tag_id__in=tag_pks).values_list(
            "article_id", flat=True
        )
    )


def _field_ids(field_names):
    if not field_names:
        return set()
    ids = set()
    for name, fid in SemanticField.objects.filter(name__in=field_names).values_list(
        "name", "id"
    ):
        ids |= article_ids_for_semantic_field(fid, include_all=True)
    return ids


def _tag_type_filter_ids(tag_string, tag_type):
    """Article ids that have this Tag (exact tag + type), or None if no filter."""
    if not tag_string:
        return None
    tag = Tag.objects.filter(tag=tag_string, type=tag_type).first()
    if not tag:
        return set()
    return set(
        ArticleIndexTag.objects.filter(tag_id=tag.id).values_list(
            "article_id", flat=True
        )
    )


def _apply_and_filters(ids, *filter_sets):
    """Intersect ids with each non-None filter set."""
    out = ids
    for fset in filter_sets:
        if fset is None:
            continue
        out = out & fset
    return out


def _fallback_count(query):
    q = _normalize_yo((query or "").strip())
    if not q:
        return 0
    core = rus_search_core(q)
    return len(core.result_ids or ())


def hydrate_group_articles(groups):
    """
    Attach full Article rows (source + additions) for wordCard templates.
    Preserves rank order from group['articles']. Debug beta: all cards visible.
    """
    ordered_ids = []
    for g in groups or []:
        for item in g.get("articles") or []:
            aid = item.get("id") if isinstance(item, dict) else None
            if aid is not None:
                ordered_ids.append(aid)
    if not ordered_ids:
        for g in groups or []:
            g["article_objs"] = []
            g["article_objs_more"] = []
            g["more"] = 0
        return groups

    additions_qs = ArticleAddition.objects.select_related("source")
    full_by_id = {
        a.pk: a
        for a in Article.objects.filter(pk__in=set(ordered_ids))
        .select_related("source")
        .prefetch_related(Prefetch("additions", queryset=additions_qs))
    }
    for g in groups:
        objs = []
        for item in g.get("articles") or []:
            aid = item.get("id") if isinstance(item, dict) else None
            if aid in full_by_id:
                objs.append(full_by_id[aid])
        g["article_objs"] = objs
        g["article_objs_more"] = []
        g["more"] = 0
    return groups


def _title_lexical(lemmas, focus=None):
    """Group title: focus (answer) wins; lexical is context, not the headline."""
    focus = list(focus or [])
    if focus:
        if len(focus) == 1:
            return f"Ответ: «{focus[0]}»"
        return "Ответ: «" + " · ".join(focus) + "»"
    if not lemmas:
        return "Прямые соответствия"
    if len(lemmas) == 1:
        return f"Слова со значением «{lemmas[0]}»"
    return "Слова со значением «" + " · ".join(lemmas) + "»"


def _title_tags(tag_strings):
    if not tag_strings:
        return "По пометам"
    names = list(
        Tag.objects.filter(tag__in=tag_strings)
        .order_by("sorting", "tag")
        .values_list("name", flat=True)
    )
    label = ", ".join(names or tag_strings)
    return label[:1].upper() + label[1:] if label else "По пометам"


def _title_fields(field_names, narrowed=False):
    if not field_names:
        return "Рядом по теме"
    if len(field_names) == 1:
        name = field_names[0]
        if narrowed:
            return f"Рядом по теме в поле «{name}»"
        return f"Смысловое поле «{name}»"
    joined = ", ".join(field_names)
    if narrowed:
        return f"Рядом по теме ({joined})"
    return "Смысловые поля: " + joined


def field_meta(field_names):
    """id + name for ontology links (order preserved)."""
    if not field_names:
        return []
    rows = SemanticField.objects.filter(name__in=field_names).values("id", "name")
    by_name = {r["name"]: r["id"] for r in rows}
    return [{"id": by_name[n], "name": n} for n in field_names if n in by_name]


# Backward-compatible alias
_field_meta = field_meta


def search_by_parsed(parsed, sort=SORT_RELEVANCE):
    """
    Build UI groups from a parse_query result dict.

    Lexical + focus + theme-narrowed field hits → one ranked group.
    Tag hits stay separate. Ranking: dict.ai.rank (focus exact ≫ lexical).

    Returns (groups, fallback_count).
    """
    sort_mode = normalize_sort(sort)
    query = (parsed or {}).get("query") or ""
    if not parsed or not parsed.get("ok") or not parsed.get("parse_ok"):
        return [], _fallback_count(query)

    # Karelian headword typed in Latin orthography (LLM skipped).
    if parsed.get("krl_headword"):
        ids = set(krl_article_ids(query))
        if not ids:
            return [], _fallback_count(query)

        articles, total = order_articles(ids, lambda _aid: 0, sort_mode)
        return (
            [
                {
                    "kind": "lexical",
                    "title": f"Статьи на «{query}»",
                    "total": total,
                    "more": 0,
                    "articles": articles,
                }
            ],
            None,
        )

    lexical = list(parsed.get("lexical") or [])
    focus = list(parsed.get("focus") or [])
    related = list(parsed.get("related") or [])
    tags = list(parsed.get("tags") or [])
    fields = list(parsed.get("fields") or [])
    place = parsed.get("place")
    dialect = parsed.get("dialect")

    focus_exact = exact_translate_ids(focus)
    focus_soft = _lemma_hit_ids(focus)
    lex_exact = exact_translate_ids(lexical)
    kw_focus = exact_keyword_ids(focus)
    kw_lex = exact_keyword_ids(lexical)

    lex_ids = _lemma_hit_ids(lexical)
    theme_ids = _theme_ids(related) | _theme_ids(lexical) | _theme_ids(focus)
    tag_ids = _tag_ids(tags)
    field_pool = _field_ids(fields)
    place_ids = _tag_type_filter_ids(place, 1)
    dialect_ids = _tag_type_filter_ids(dialect, 4)

    lex_ids = _apply_and_filters(lex_ids, place_ids, dialect_ids)
    tag_ids = _apply_and_filters(tag_ids, place_ids, dialect_ids)
    field_pool = _apply_and_filters(field_pool, place_ids, dialect_ids)
    focus_exact = _apply_and_filters(focus_exact, place_ids, dialect_ids)
    focus_soft = _apply_and_filters(focus_soft, place_ids, dialect_ids)

    field_narrowed = False
    if fields and field_pool:
        if related or lexical or focus:
            field_ids = field_pool & theme_ids
            field_narrowed = True
        else:
            field_ids = field_pool
    else:
        field_ids = set()

    main_ids = set()
    if lexical and lex_ids:
        main_ids |= lex_ids
    if focus_exact or focus_soft:
        main_ids |= focus_exact | focus_soft
    if field_ids:
        main_ids |= field_ids

    def score(aid):
        return relevance_score(
            aid,
            focus_exact=focus_exact,
            focus_soft=focus_soft,
            lex_exact=lex_exact,
            kw_focus=kw_focus,
            kw_lex=kw_lex,
            lex_ids=lex_ids,
            theme_ids=theme_ids,
            tag_ids=tag_ids,
            field_pool=field_pool,
        )

    def _group(kind, title, ids):
        articles, total = order_articles(ids, score, sort_mode)
        return {
            "kind": kind,
            "title": title,
            "total": total,
            "more": 0,
            "articles": articles,
        }

    groups = []
    if main_ids:
        if focus or (lexical and lex_ids):
            title = _title_lexical(lexical, focus=focus)
        elif fields:
            title = _title_fields(fields, narrowed=field_narrowed)
        else:
            title = "Результаты"
        g = _group("lexical", title, main_ids)
        if fields:
            g["fields"] = _field_meta(fields)
        groups.append(g)
    if tags and tag_ids:
        groups.append(_group("tag", _title_tags(tags), tag_ids))

    groups.sort(key=lambda g: KIND_ORDER.index(g["kind"]))

    if not groups:
        return [], _fallback_count(query)
    return groups, None


def check_benchmark_case(parsed, case):
    """Soft checks for one benchmark case. Returns (ok, detail)."""
    problems = []
    for needle in case.get("lexical_contains") or []:
        if needle not in (parsed.get("lexical") or []):
            problems.append(f"lexical missing {needle!r}")
    for needle in case.get("focus_contains") or []:
        if needle not in (parsed.get("focus") or []):
            problems.append(f"focus missing {needle!r}")
    tags_any = case.get("tags_any") or []
    if tags_any:
        have = set(parsed.get("tags") or [])
        if not have.intersection(tags_any):
            problems.append(f"tags_any none of {tags_any}")
    dropped = [d.lower() for d in (parsed.get("dropped") or [])]
    for needle in case.get("dropped_contains") or []:
        n = needle.lower()
        if n not in dropped and not any(n in d or d in n for d in dropped):
            problems.append(f"dropped missing {needle!r}")
    for forbidden in case.get("must_not_have_tags") or []:
        if forbidden in (parsed.get("tags") or []):
            problems.append(f"unexpected tag {forbidden!r}")
    fields_any = case.get("fields_any") or []
    if fields_any:
        have = set(parsed.get("fields") or [])
        if not have.intersection(fields_any):
            problems.append(f"fields_any none of {fields_any}")
    if case.get("require_parse_ok") and not parsed.get("parse_ok"):
        problems.append("parse_ok expected")
    if case.get("require_ok") and not parsed.get("ok"):
        problems.append("ok expected")
    return (not problems), "; ".join(problems)


def run_benchmarks(cases, parse_fn):
    """
    cases: list of dicts with query + soft expectations.
    parse_fn: callable(query) -> parse result (usually parse_query).
    """
    results = []
    for case in cases:
        query = case.get("query") or ""
        parsed = parse_fn(query)
        ok, detail = check_benchmark_case(parsed, case)
        results.append({"query": query, "ok": ok, "detail": detail, "parsed": parsed})
    return results
