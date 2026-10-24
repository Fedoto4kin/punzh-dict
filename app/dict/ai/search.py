"""
Deterministic retrieval for AI search: axes from parse_query → result groups.

No second LLM call. Reuses dict.search primitives (rus_search_core,
article_ids_for_semantic_field, ArticleIndexTag).
"""

from __future__ import annotations

from django.db.models import Count, Prefetch, Q

from dict.ai.query_parse import fields_matching_lemmas
from dict.ai.rank import (
    SORT_ALPHA,
    SORT_RELEVANCE,
    exact_keyword_ids,
    exact_translate_ids,
    normalize_sort,
    order_articles,
    relevance_score,
)
from dict.models import (
    Article,
    ArticleAddition,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleKeyword,
    ArticleSemanticField,
    SemanticField,
    Tag,
)
from dict.search import (
    _query_tokens,
    _token_boundary_regex,
    article_ids_for_semantic_field,
    expand_by_links,
    krl_article_ids,
    rus_search_core,
)

# Debug beta: show every card (no «ещё N» collapse). Kept as aliases for tests.
TOP_N = None  # None = unlimited
FIELD_TOP_N = None
KIND_ORDER = ("lexical", "tag")  # field merged into lexical/main


def _normalize_yo(text):
    return (text or "").translate(str.maketrans({"ё": "е"}))


def _multiword_lemma_ids(lemma):
    """
    Multi-word lemma → same rus_word must contain every token (AND).

    Avoids token-OR false friends: «родственные связи» must not rank
    «половую связь» as a focus/lexical hit via the lone token «связи».
    """
    toks = _query_tokens(_normalize_yo(lemma))
    if len(toks) < 2:
        return set()
    q = Q()
    for tok in toks:
        q &= Q(rus_word__iregex=_token_boundary_regex(tok))
    return set(
        ArticleIndexTranslate.objects.filter(q).values_list("article_id", flat=True)
    )


def _lemma_hit_ids(lemmas, *, expand_links=False):
    """
    Articles matching any lemma via the translation index.

    Single-token lemmas: same soft match as rus_search_core (token + fuzzy).
    Multi-word lemmas: AND of all tokens inside one rus_word (not OR across
    the phrase). Lemmas are OR-ed with each other.

    Default expand_links=False so AI search can demote см./от pull-ins
    separately; classical /search/ still expands inside rus_search_core.
    """
    if not lemmas:
        return set()
    ids = set()
    for raw in lemmas:
        lem = _normalize_yo((raw or "").strip())
        if not lem:
            continue
        toks = _query_tokens(lem)
        if len(toks) >= 2:
            ids |= _multiword_lemma_ids(lem)
        else:
            core = rus_search_core(lem, expand_links=False)
            ids |= set(core.result_ids or ())
    if expand_links and ids:
        ids = set(expand_by_links(ids))
    return ids


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
    """
    Articles matching tags. Several tags → intersection (AND):
    «примета» ∩ «v» = verbs marked as omens.
    """
    if not tag_strings:
        return set()
    ids = None
    for tag in tag_strings:
        tag = (tag or "").strip()
        if not tag:
            continue
        hit = set(
            ArticleIndexTag.objects.filter(tag__tag=tag).values_list(
                "article_id", flat=True
            )
        )
        ids = hit if ids is None else (ids & hit)
    return ids or set()


def _split_pos_tags(tag_strings):
    """
    Split hard tags into POS (Tag.type=2) vs the rest.

    POS must only narrow an existing candidate set, never replace it with
    field∩v (thousands of verbs). Stylistic/other hard tags keep browse/AND.
    """
    tags = [t for t in (tag_strings or []) if (t or "").strip()]
    if not tags:
        return [], [], set(), set()
    pos_codes = set(
        Tag.objects.filter(tag__in=tags, type=2).values_list("tag", flat=True)
    )
    pos = [t for t in tags if t in pos_codes]
    other = [t for t in tags if t not in pos_codes]
    return other, pos, _tag_ids(other), _tag_ids(pos)


def _field_ids(field_names, *, include_referrers=True):
    if not field_names:
        return set()
    ids = set()
    for name, fid in SemanticField.objects.filter(name__in=field_names).values_list(
        "name", "id"
    ):
        ids |= article_ids_for_semantic_field(
            fid, include_all=True, include_referrers=include_referrers
        )
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


TITLE_MAIN = "Нашлось по запросу"


def _field_names_frequent_among(article_ids, limit=4):
    """Top SemanticField.name by assignment count on these articles."""
    if not article_ids or limit <= 0:
        return []
    rows = (
        ArticleSemanticField.objects.filter(article_id__in=article_ids)
        .values("field__name")
        .annotate(c=Count("id"))
        .order_by("-c", "field__name")[:limit]
    )
    return [r["field__name"] for r in rows if r.get("field__name")]


def _enrich_fields(fields, focus, related, lexical):
    """
    Union LLM fields with fields frequent among theme seeds.
    Seeds: focus → lexical → related (lexical before related so
    «про животных» wins over «поведение» invented from «примета»).
    First pass: translation-index hits; second: keywords if still thin.
    """
    out = []
    seen = set()
    for name in list(fields or []):
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    seed = list(focus or []) + list(lexical or []) + list(related or [])
    # 1) translations → fields
    for name in _field_names_frequent_among(_lemma_hit_ids(seed), limit=4):
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    # 2) broader (keywords) if still thin
    if len(out) < 2:
        for name in _field_names_frequent_among(_keyword_hit_ids(seed), limit=4):
            if name and name not in seen:
                seen.add(name)
                out.append(name)
    return out


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
    tags_soft = list(parsed.get("tags_soft") or [])
    llm_fields = list(parsed.get("fields") or [])
    place = parsed.get("place")
    dialect = parsed.get("dialect")
    # Dialect/place + lemma in a field label («погода» → «Природа и погода»):
    # keep LLM/label fields only (no enrich neighbors). Tiers:
    #   1) lexical/focus hits that are in theme∩говор
    #   2) then the rest of theme∩говор
    # Relax говор only when theme∩говор is empty.
    field_defs = dict(SemanticField.objects.values_list("name", "definition"))
    matched_label_fields = fields_matching_lemmas(
        list(lexical) + list(focus), field_defs
    )
    label_theme = bool((dialect or place) and matched_label_fields)
    if label_theme:
        fields = list(llm_fields) or list(matched_label_fields)
        theme_fields = list(fields)
    else:
        # Theme for marks∩field: lexical/focus only (ignore related from «примета»).
        theme_fields = _enrich_fields(llm_fields, focus, [], lexical)
        fields = _enrich_fields(llm_fields, focus, related, lexical)

    focus_exact = exact_translate_ids(focus)
    focus_soft = _lemma_hit_ids(focus)
    lex_exact = exact_translate_ids(lexical)
    kw_focus = exact_keyword_ids(focus)
    kw_lex = exact_keyword_ids(lexical)

    # Raw (pre dialect/place) sets — needed to relax говор without dumping all всг.
    lex_ids_raw = _lemma_hit_ids(lexical)
    theme_tr_raw = (
        _lemma_hit_ids(related) | _lemma_hit_ids(lexical) | _lemma_hit_ids(focus)
    )
    theme_kw_raw = (
        _keyword_hit_ids(related) | _keyword_hit_ids(lexical) | _keyword_hit_ids(focus)
    )
    theme_ids_raw = theme_tr_raw | theme_kw_raw
    hard_tag_ids_raw = _tag_ids(tags)
    soft_tag_ids_raw = _tag_ids(tags_soft)
    field_pool_raw = _field_ids(fields, include_referrers=False)
    primary_theme = (theme_fields[:1] if theme_fields else fields[:1]) or []
    primary_field_pool_raw = _field_ids(primary_theme, include_referrers=False)
    place_ids = _tag_type_filter_ids(place, 1)
    dialect_ids = _tag_type_filter_ids(dialect, 4)
    has_theme = bool(fields or lexical or focus or related)

    lex_ids = _apply_and_filters(lex_ids_raw, place_ids, dialect_ids)
    hard_tag_ids = _apply_and_filters(hard_tag_ids_raw, place_ids, dialect_ids)
    soft_tag_ids = _apply_and_filters(soft_tag_ids_raw, place_ids, dialect_ids)
    field_pool = _apply_and_filters(field_pool_raw, place_ids, dialect_ids)
    primary_field_pool = _apply_and_filters(
        primary_field_pool_raw, place_ids, dialect_ids
    )
    focus_exact = _apply_and_filters(focus_exact, place_ids, dialect_ids)
    focus_soft = _apply_and_filters(focus_soft, place_ids, dialect_ids)
    theme_tr = _apply_and_filters(theme_tr_raw, place_ids, dialect_ids)
    theme_kw = _apply_and_filters(theme_kw_raw, place_ids, dialect_ids)
    theme_ids = theme_tr | theme_kw

    def _field_contour(pool, tr, kw):
        """Field ∩ theme (tr/kw), or whole pool when no lemmas."""
        if not (fields and pool):
            return set(), set()
        if related or lexical or focus:
            tr_ids = pool & tr
            return tr_ids, tr_ids | (pool & kw)
        return set(), set(pool)

    def _content_from(lex, f_exact, f_soft):
        out = set()
        if lexical and lex:
            out |= lex
        if f_exact or f_soft:
            out |= f_exact | f_soft
        return out

    # Field contour: (1) field ∩ translations, (2) field ∩ keywords.
    field_tr_ids, field_ids = _field_contour(field_pool, theme_tr, theme_kw)
    content_ids = _content_from(lex_ids, focus_exact, focus_soft)
    # With an explicit theme field, lexical hits outside it are noise under
    # dialect («погода» on a Состояние∩всг. article ≠ weather browse).
    # Empty field_pool (theme∩говор = ∅) must clear content, not keep noise.
    if fields and content_ids:
        content_ids &= field_pool

    # Hard tags: stylistic/other may AND or browse field∩mark. POS (type 2)
    # only narrows later — never main = field∩v.
    other_tags, pos_tags, other_ids, pos_ids = _split_pos_tags(tags)
    other_ids = _apply_and_filters(other_ids, place_ids, dialect_ids)
    pos_ids = _apply_and_filters(pos_ids, place_ids, dialect_ids)
    tags_hard_active = list(other_tags) + list(pos_tags)
    tag_ids = set(hard_tag_ids) | set(soft_tag_ids)
    dialect_relaxed = False
    place_relaxed = False
    active_place_ids = place_ids
    active_dialect_ids = dialect_ids

    # Lexical anchors in theme∩говор (translations/focus only — not KW illustrations).
    lex_vsg = set()
    if (dialect_ids or place_ids) and field_pool_raw and (lexical or focus):
        lex_vsg = _content_from(
            _apply_and_filters(lex_ids_raw, place_ids, dialect_ids),
            _apply_and_filters(exact_translate_ids(focus), place_ids, dialect_ids),
            _apply_and_filters(_lemma_hit_ids(focus), place_ids, dialect_ids),
        )
        lex_vsg &= field_pool_raw

    if label_theme and not other_tags:
        # Tier 1: lexical∩тема∩говор; tier 2: rest of тема∩говор.
        theme_vsg = set(primary_field_pool or field_pool)
        main_ids = set(lex_vsg) | theme_vsg
        content_ids = set(lex_vsg)
        if theme_vsg:
            field_pool = theme_vsg
            if primary_theme:
                fields = (
                    list(primary_theme) if len(primary_theme) == 1 else list(fields)
                )
        # Scoring: only dialect lexical anchors count as lex hits.
        lex_ids = set(lex_vsg)
        field_tr_ids = set(lex_vsg)
    elif other_tags and other_ids:
        field_tag = (primary_field_pool & other_ids) if primary_field_pool else set()
        if field_tag:
            main_ids = set(field_tag)
        elif content_ids:
            main_ids = content_ids & other_ids
            if field_ids:
                main_ids |= field_ids & other_ids
            if not main_ids:
                main_ids = set(content_ids)
                if field_ids:
                    main_ids |= field_ids
                tags_hard_active = list(pos_tags)  # dropped stylistic; POS may remain
                other_tags = []
        else:
            main_ids = set(other_ids)
    else:
        main_ids = set(content_ids)
        if field_tr_ids:
            main_ids |= field_tr_ids
        if field_ids:
            main_ids |= field_ids
        if other_tags and not other_ids:
            # Named hard mark with no articles — ignore mark, keep content.
            tags_hard_active = list(pos_tags)
            other_tags = []

    # Empty after dialect/place AND: browse theme∩говор, else relax говор.
    if not main_ids:
        if has_theme:
            browse_names = list(llm_fields) or list(primary_theme) or list(fields)
            browse_pool = _apply_and_filters(
                _field_ids(browse_names, include_referrers=False),
                place_ids,
                dialect_ids,
            )
            if not browse_pool and primary_field_pool:
                browse_pool = set(primary_field_pool)
            if browse_pool:
                main_ids = set(browse_pool)
                if browse_names:
                    fields = list(browse_names)
                    field_pool = set(browse_pool)
                    primary_theme = browse_names[:1]
                    primary_field_pool = set(browse_pool)
            else:
                # No hits in говор for this theme → drop dialect/place, keep lemmas.
                dialect_relaxed = bool(dialect_ids)
                place_relaxed = bool(place_ids)
                active_place_ids = None
                active_dialect_ids = None
                browse_names = list(llm_fields) or list(primary_theme) or list(fields)
                field_pool = _field_ids(browse_names, include_referrers=False)
                primary_field_pool = _field_ids(
                    browse_names[:1] if browse_names else [], include_referrers=False
                )
                if browse_names:
                    fields = list(browse_names)
                    primary_theme = browse_names[:1]
                lex_ids = lex_ids_raw
                theme_tr = theme_tr_raw
                theme_kw = theme_kw_raw
                theme_ids = theme_ids_raw
                focus_exact = exact_translate_ids(focus)
                focus_soft = _lemma_hit_ids(focus)
                hard_tag_ids = hard_tag_ids_raw
                soft_tag_ids = soft_tag_ids_raw
                _, pos_tags, other_ids, pos_ids = _split_pos_tags(tags)
                other_ids = set(other_ids)
                pos_ids = set(pos_ids)
                tag_ids = set(hard_tag_ids) | set(soft_tag_ids)
                field_tr_ids, field_ids = _field_contour(field_pool, theme_tr, theme_kw)
                content_ids = _content_from(lex_ids, focus_exact, focus_soft)
                if fields and content_ids:
                    content_ids &= field_pool
                main_ids = set(content_ids)
                if field_ids:
                    main_ids |= field_ids
        elif dialect_ids:
            main_ids = set(dialect_ids)
        elif place_ids:
            main_ids = set(place_ids)

    # POS tightens only: intersect base, never replace with all verbs in a field.
    if pos_ids:
        if main_ids:
            narrowed = main_ids & pos_ids
            if narrowed:
                main_ids = narrowed
            else:
                # No POS hits among candidates — drop POS, keep theme/lex.
                tags_hard_active = [t for t in tags_hard_active if t not in pos_tags]
                pos_tags = []
        else:
            # POS-only browse («глаголы»).
            main_ids = set(pos_ids)

    # Soft marks: never AND, but do enter candidates so ranking can surface them.
    # Applied after POS so soft∩field (e.g. бранн.) is not wiped by v.
    # With a field → soft ∩ field (bounded). Else only if main still empty.
    if soft_tag_ids:
        if field_pool:
            main_ids |= soft_tag_ids & field_pool
        elif not main_ids:
            main_ids |= set(soft_tag_ids)

    # One hop of incoming см./от only (stubs → hit), not outgoing hit → target.
    direct_ids = set(main_ids)
    main_ids = _apply_and_filters(
        expand_by_links(direct_ids, sides="incoming"),
        active_place_ids,
        active_dialect_ids,
    )
    demote_ids = main_ids - direct_ids
    # No own translations (KW/illustration-only) → same demote tier as см./от.
    if main_ids:
        with_tr = set(
            ArticleIndexTranslate.objects.filter(article_id__in=main_ids)
            .values_list("article_id", flat=True)
            .distinct()
        )
        demote_ids |= main_ids - with_tr

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
            field_tr_ids=field_tr_ids,
        )

    def _group(kind, title, ids):
        articles, total = order_articles(
            ids,
            score,
            sort_mode,
            demote_ids=demote_ids if sort_mode != SORT_ALPHA else None,
        )
        return {
            "kind": kind,
            "title": title,
            "total": total,
            "more": 0,
            "articles": articles,
            "demote_ids": list(demote_ids if sort_mode != SORT_ALPHA else ()),
        }

    groups = []
    if main_ids:
        g = _group("lexical", TITLE_MAIN, main_ids)
        if tags_hard_active and primary_theme:
            g["fields"] = _field_meta(primary_theme)
        elif fields:
            g["fields"] = _field_meta(fields)
        if tags_hard_active:
            g["tags"] = list(tags_hard_active)
        if tags_soft:
            g["tags_soft"] = list(tags_soft)
        if dialect:
            g["dialect"] = dialect
            if dialect_relaxed:
                g["dialect_relaxed"] = True
        if place:
            g["place"] = place
            if place_relaxed:
                g["place_relaxed"] = True
        groups.append(g)

    groups.sort(key=lambda g: KIND_ORDER.index(g["kind"]))

    if not groups:
        return [], _fallback_count(query)
    return groups, None


def _fold_lemma(text):
    return (text or "").casefold().replace("ё", "е")


def check_benchmark_case(parsed, case):
    """Soft checks for one benchmark case. Returns (ok, detail)."""
    problems = []
    lexical = list(parsed.get("lexical") or [])
    lexical_folded = {_fold_lemma(x) for x in lexical}
    for needle in case.get("lexical_contains") or []:
        if needle not in lexical:
            problems.append(f"lexical missing {needle!r}")
    lexical_any = case.get("lexical_any") or []
    if lexical_any and not lexical_folded.intersection(
        _fold_lemma(x) for x in lexical_any
    ):
        problems.append(f"lexical_any none of {lexical_any}")
    focus = list(parsed.get("focus") or [])
    for needle in case.get("focus_contains") or []:
        if needle not in focus:
            problems.append(f"focus missing {needle!r}")
    tags = list(parsed.get("tags") or [])
    for needle in case.get("tags_contains") or []:
        if needle not in tags:
            problems.append(f"tags missing {needle!r}")
    if case.get("dialect") and parsed.get("dialect") != case["dialect"]:
        problems.append(f"dialect {parsed.get('dialect')!r} != {case['dialect']!r}")
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
        if forbidden in tags:
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
