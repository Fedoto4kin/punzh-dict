"""Karelian word search, tag facets, and tag-listing search."""

import re
from collections import defaultdict

from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Count, F, Q
from django.db.models.functions import Length

from dict.helpers import (
    build_pagination_hints,
    fold_interior_hyphens,
    strip_krl_apostrophes,
)
from dict.models import (
    Article,
    ArticleIndexTag,
    ArticleIndexWord,
    ArticleIndexWordNormalization,
    Levenshtein,
    Tag,
)

from .common import Content, get_sorted_articles, num_by_page, sort_and_paginate


# Same mapping the public search form applies before ILIKE: '.' is one
# character, '?' is any sequence; sibilants and ü/y fold like the word index.
# Apostrophes: KRL_APOSTROPHES via strip_krl_apostrophes (shared with indexing).
# Parentheses: optional endings like igävähkö(n’e) / kurpa(t) — drop marks,
# keep contents (same as gen_word_variants and see-link hrefs).
_KRL_ILIKE_TRANS = str.maketrans(
    {
        ";": "",
        ",": "",
        "(": "",
        ")": "",
        "š": "s",
        "č": "c",
        "ž": "z",
        "ü": "y",
        "Ü": "Y",
        "…": "",
        "?": "%",
        ".": "_",
    }
)


def prepare_krl_ilike_query(query: str) -> str:
    return fold_interior_hyphens(
        strip_krl_apostrophes(query).translate(_KRL_ILIKE_TRANS)
    )


def krl_article_ids(query: str):
    pattern = prepare_krl_ilike_query(query)
    return ArticleIndexWord.objects.filter(word__ilike=pattern).values_list(
        "article_id", flat=True
    )


# Facet groups for Karelian search tag filters (same Tag.type buckets as /tags/,
# except type 5 — boolean «с фразеологизмами» via ?ph=1, not radio chips).
# Grammar (type 2): only parent labels (level=0); children like comparativus stay
# on the subject index only.
_KRL_TAG_GROUP_ORDER = (2, 3, 1, 4)
_KRL_TAG_GROUP_TITLES = {
    1: "Населенные пункты",
    2: "Грамматические пометы",
    3: "Нормативно-стилистические и экспрессивно-оценочные пометы",
    4: "Говоры",
}
_KRL_PHRASE_TAG_TYPE = 5
_KRL_PHRASE_LABEL = "словарные статьи с фразеологизмами"


def parse_krl_tag_param(raw):
    """Parse ?t=12,34 into a list of ints; empty / junk -> []."""
    if not raw or not str(raw).strip():
        return []
    out = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def parse_krl_phrase_param(raw):
    """True when ?ph=1 (or true/yes/on)."""
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def normalize_krl_tag_ids(tag_ids):
    """
    At most one tag per Tag.type; drop unknown ids, grammar children (level=1),
    and type=5 (phraseologism — use ?ph=1 instead).
    Order follows _KRL_TAG_GROUP_ORDER for stable ?t= query strings.
    """
    if not tag_ids:
        return []
    rows = list(Tag.objects.filter(id__in=tag_ids).values_list("id", "type", "level"))
    by_id = {tid: (ttype, level) for tid, ttype, level in rows}
    chosen = {}
    for tid in tag_ids:
        meta = by_id.get(tid)
        if meta is None:
            continue
        ttype, level = meta
        if ttype == _KRL_PHRASE_TAG_TYPE:
            continue
        if ttype == 2 and level != 0:
            continue
        if ttype in chosen:
            continue
        chosen[ttype] = tid
    return [chosen[t] for t in _KRL_TAG_GROUP_ORDER if t in chosen]


def format_krl_filter_query(tag_ids, phrase=False, include_all=False):
    """GET suffix for ?t= / ?ph= / ontology ?all=1 (illustrations mode)."""
    parts = []
    if tag_ids:
        parts.append("t=" + ",".join(str(i) for i in tag_ids))
    if phrase:
        parts.append("ph=1")
    if include_all:
        parts.append("all=1")
    return ("?" + "&".join(parts)) if parts else ""


def parse_ontology_all_param(raw):
    """True when ?all=1 — ontology listing includes illustration-only fields."""
    return parse_krl_phrase_param(raw)


def format_krl_t_query(tag_ids):
    """Backward-compatible alias: tags only, no ?ph=."""
    return format_krl_filter_query(tag_ids, phrase=False)


def article_ids_with_phraseologism():
    """Articles that have any Tag.type=5 (фразеологизмы) index row."""
    return set(
        ArticleIndexTag.objects.filter(tag__type=_KRL_PHRASE_TAG_TYPE).values_list(
            "article_id", flat=True
        )
    )


def _tag_ids_without_type(selected_ids, type_id):
    if not selected_ids:
        return []
    drop = set(
        Tag.objects.filter(id__in=selected_ids, type=type_id).values_list(
            "id", flat=True
        )
    )
    return [tid for tid in selected_ids if tid not in drop]


def _facet_eligible_tag_rows(article_ids):
    """
    (tag_id, type, name, sorting) for radio-facet tags on articles.
    Grammar type=2: parents only (level=0). Type 5 excluded (boolean ?ph=).
    """
    if not article_ids:
        return []
    q = (
        ArticleIndexTag.objects.filter(article_id__in=article_ids)
        .exclude(tag__type=_KRL_PHRASE_TAG_TYPE)
        .exclude(tag__type=2, tag__level=1)
        .values_list("tag_id", "tag__type", "tag__name", "tag__sorting")
        .distinct()
    )
    return list(q)


def _apply_krl_filters(base_ids, selected_ids, phrase, exclude_type=None):
    ids = set(base_ids)
    sel = (
        _tag_ids_without_type(selected_ids, exclude_type)
        if exclude_type is not None
        else list(selected_ids or [])
    )
    if sel:
        ids &= article_ids_by_tags(sel)
    if phrase:
        ids &= article_ids_with_phraseologism()
    return ids


def krl_tag_facets(base_ids, selected_ids, phrase=False):
    """
    Facet UI for KRL search: (groups, phrase_filter).

    groups — radio chip groups (≥2 options each), or [].
    phrase_filter — dict for the phraseologism checkbox, or None.
    Empty ( [], None) when the whole filter block should be hidden.
    """
    base_ids = set(base_ids)
    selected_ids = list(selected_ids or [])
    phrase = bool(phrase)
    if not base_ids:
        return [], None

    eligible_in_base = _facet_eligible_tag_rows(base_ids)
    ph_ids = article_ids_with_phraseologism()
    phrase_diverse = bool((base_ids & ph_ids) and (base_ids - ph_ids))
    wide = (
        len(base_ids) > num_by_page
        or len({r[0] for r in eligible_in_base}) >= 2
        or phrase_diverse
    )
    if not wide:
        return [], None

    selected_types = dict(
        Tag.objects.filter(id__in=selected_ids).values_list("id", "type")
    )
    groups = []
    for ttype in _KRL_TAG_GROUP_ORDER:
        facet_ids = _apply_krl_filters(
            base_ids, selected_ids, phrase, exclude_type=ttype
        )
        rows = _facet_eligible_tag_rows(facet_ids)
        options_map = {}
        for tid, row_type, name, sorting in rows:
            if row_type != ttype:
                continue
            options_map[tid] = (name, sorting if sorting is not None else 10**9)
        selected_in_group = next(
            (tid for tid in selected_ids if selected_types.get(tid) == ttype),
            None,
        )
        if selected_in_group:
            # Keep the active chip visible even when narrowing left only one
            # tag of this type; do not list siblings that are not in play.
            if selected_in_group not in options_map:
                row = (
                    Tag.objects.filter(pk=selected_in_group)
                    .values_list("name", "sorting")
                    .first()
                )
                if row:
                    name, sorting = row
                    options_map[selected_in_group] = (
                        name,
                        sorting if sorting is not None else 10**9,
                    )
            options_map = {
                tid: meta
                for tid, meta in options_map.items()
                if tid == selected_in_group
            }
        elif len(options_map) < 2:
            continue
        if not options_map:
            continue
        sel_wo = _tag_ids_without_type(selected_ids, ttype)
        options = []
        for tid, (name, sorting) in sorted(
            options_map.items(), key=lambda item: (item[1][1], item[1][0], item[0])
        ):
            selected = tid == selected_in_group
            # Active chip toggles off (same as phrase ?ph=); inactive selects.
            if selected:
                t_query = format_krl_filter_query(sel_wo, phrase=phrase)
            else:
                new_sel = normalize_krl_tag_ids(sel_wo + [tid])
                t_query = format_krl_filter_query(new_sel, phrase=phrase)
            options.append(
                {
                    "id": tid,
                    "label": name,
                    "selected": selected,
                    "t_query": t_query,
                }
            )
        groups.append(
            {
                "type": ttype,
                "title": _KRL_TAG_GROUP_TITLES[ttype],
                "options": options,
                "clear_t_query": format_krl_filter_query(sel_wo, phrase=phrase),
            }
        )

    # Phrase as its own untitled group (chip style), after stylistic (type 3).
    tagged_only = _apply_krl_filters(base_ids, selected_ids, phrase=False)
    with_ph = tagged_only & ph_ids
    without_ph = tagged_only - ph_ids
    phrase_filter = None
    if phrase or (with_ph and without_ph):
        phrase_filter = {
            "checked": phrase,
            "label": _KRL_PHRASE_LABEL,
            "t_query": format_krl_filter_query(selected_ids, phrase=not phrase),
        }
        phrase_group = {
            "type": "ph",
            "title": None,
            "options": [
                {
                    "id": "ph",
                    "label": phrase_filter["label"],
                    "selected": phrase_filter["checked"],
                    "t_query": phrase_filter["t_query"],
                }
            ],
            "clear_t_query": format_krl_filter_query(selected_ids, phrase=False),
        }
        # After stylistic (3); else after grammar (2); else before areal (1/4); else end.
        insert_at = len(groups)
        for i, g in enumerate(groups):
            if g["type"] == 3:
                insert_at = i + 1
                break
        else:
            for i, g in enumerate(groups):
                if g["type"] in (1, 4):
                    insert_at = i
                    break
                if g["type"] == 2:
                    insert_at = i + 1
        groups.insert(insert_at, phrase_group)

    if not groups:
        return [], None
    return groups, phrase_filter


def tag_filters_from_request(request):
    """Parse and normalize ?t= / ?ph= from a Django request."""
    tag_ids = normalize_krl_tag_ids(parse_krl_tag_param(request.GET.get("t")))
    phrase = parse_krl_phrase_param(request.GET.get("ph"))
    return tag_ids, phrase


def tag_filtered_ids_and_facets(
    base_ids, tag_ids=None, phrase=False, include_all=False
):
    """
    Apply tag/?ph filters to a base article-id set and build facet UI data.

    Shared by KRL /search/ and /ontology/. Returns
    (filtered_ids, tag_filter_groups, phrase_filter, t_query).
    include_all — ontology illustrations mode (?all=1) in facet/pagination queries.
    """
    selected = normalize_krl_tag_ids(tag_ids or [])
    phrase = bool(phrase)
    include_all = bool(include_all)
    base_ids = set(base_ids)
    filtered_ids = _apply_krl_filters(base_ids, selected, phrase)
    groups, phrase_filter = krl_tag_facets(base_ids, selected, phrase)
    if include_all:
        groups = _ontology_queries_with_all(groups)
        if phrase_filter is not None:
            phrase_filter = dict(phrase_filter)
            phrase_filter["t_query"] = _with_all_param(phrase_filter["t_query"])
    return (
        filtered_ids,
        groups,
        phrase_filter,
        format_krl_filter_query(selected, phrase, include_all=include_all),
    )


def _with_all_param(t_query):
    """Append ontology ?all=1 / &all=1 to a filter query string."""
    if not t_query:
        return "?all=1"
    if "all=1" in t_query:
        return t_query
    return t_query + "&all=1"


def _ontology_queries_with_all(groups):
    if not groups:
        return groups
    out = []
    for group in groups:
        g = dict(group)
        if g.get("clear_t_query") is not None:
            g["clear_t_query"] = _with_all_param(g["clear_t_query"])
        opts = []
        for opt in g.get("options") or []:
            o = dict(opt)
            o["t_query"] = _with_all_param(o.get("t_query") or "")
            opts.append(o)
        g["options"] = opts
        out.append(g)
    return out


def word_search(query: str, page: int, tag_ids=None, phrase=False):
    """
    Karelian headword search, optional ?t= / ?ph= filters.

    Returns (page_obj, found_count, tag_filter_groups, phrase_filter, t_query).
    """
    filtered_ids, groups, phrase_filter, t_query = tag_filtered_ids_and_facets(
        krl_article_ids(query), tag_ids, phrase
    )
    page_obj, found_count = get_sorted_articles(filtered_ids, page)
    return page_obj, found_count, groups, phrase_filter, t_query


# ------------------------------------------------------------
#  Поиск возможных слов
# ------------------------------------------------------------


def search_possible(query: str) -> set:
    # Fold like the word index; strip ?/. so they are not ILIKE wildcards here.
    folded = prepare_krl_ilike_query(re.sub(r"[?.]", "", query or "")).lower()

    def search_levenshtein(q: str):
        return (
            ArticleIndexWordNormalization.objects.annotate(
                lev_dist=Levenshtein(F("word"), q)
            )
            .filter(lev_dist__lte=2)
            .order_by("-lev_dist", Length("word").asc())
        )

    def search_trigram(q: str):
        return (
            ArticleIndexWordNormalization.objects.annotate(
                similarity=TrigramSimilarity("word", q),
            )
            .filter(similarity__gt=0.2)
            .order_by("-similarity", Length("word").asc())
        )

    if not folded:
        return set()

    return set(
        w.word for w in (set(search_trigram(folded)) & set(search_levenshtein(folded)))
    )


# ------------------------------------------------------------
#  Поиск по тегам
# ------------------------------------------------------------


def get_tags_by_type(type_id=None) -> set:
    if type_id:
        return Tag.objects.filter(type=type_id).order_by("sorting", "name")
    return Tag.objects.all()


def get_tags_by_ids_distinct(ids: []) -> set:
    return set(Tag.objects.filter(id__in=ids).values_list("name", flat=True))


def compatible_disable(selected):
    """
    Given selected tag ids (>=1), return the tag ids to DISABLE.

    A candidate tag k of group G is AVAILABLE iff there is at least one article
    matching (the selection WITHOUT group G) AND k. I.e. a tag is checked
    against the OTHER groups' selection, not against the full current result:
    within its own group tags combine by OR, but that OR must still intersect
    (AND) the other groups. Otherwise k is disabled.

    This correctly disables a second tag in an already-selected group when it
    is incompatible with the other groups (e.g. selecting a dialect + one
    stylistic pomета must still grey out stylistic pometы that never co-occur
    with that dialect).
    """
    if not selected:
        return []

    # тип каждого выбранного тега
    sel_types = dict(Tag.objects.filter(id__in=selected).values_list("id", "type"))
    selected_set = set(selected)

    # base без каждой группы кешируем (групп мало)
    base_cache = {}

    def base_without_group(g):
        if g not in base_cache:
            sel_wo = [t for t in selected if sel_types.get(t) != g]
            base_cache[g] = article_ids_by_tags(sel_wo)
        return base_cache[g]

    # статьи по каждому тегу-кандидату берём пачкой: tag_id -> set(article_id)
    # (для всех тегов сразу, один запрос)
    articles_by_tag = {}
    for tid, aid in ArticleIndexTag.objects.values_list("tag_id", "article_id"):
        articles_by_tag.setdefault(tid, set()).add(aid)

    disable = []
    for tid, ttype in Tag.objects.values_list("id", "type"):
        if tid in selected_set:
            continue
        base = base_without_group(ttype)
        arts = articles_by_tag.get(tid, set())
        if not (base & arts):
            disable.append(tid)
    return disable


def article_ids_by_tags(tag_ids):
    """
    Article ids matching a flat set of tag ids: OR within a Tag.type group,
    AND between groups. Empty tag_ids -> all articles (no constraint).
    Reads ArticleIndexTag. Returns set(article_id).
    """
    if not tag_ids:
        return set(Article.objects.values_list("id", flat=True))

    groups = {}
    for tid, ttype in Tag.objects.filter(id__in=tag_ids).values_list("id", "type"):
        groups.setdefault(ttype, []).append(tid)

    result = None
    for ttype, ids in groups.items():
        matched = set(
            ArticleIndexTag.objects.filter(tag_id__in=ids).values_list(
                "article_id", flat=True
            )
        )
        result = matched if result is None else (result & matched)
    return result if result is not None else set()


def search_by_tags_smart(by_geo, by_tags, by_ling, by_dialect, by_other, page):
    all_tag_ids = (
        list(by_geo) + list(by_tags) + list(by_ling) + list(by_dialect) + list(by_other)
    )
    articles_ids = article_ids_by_tags(all_tag_ids)

    articles = Article.objects.filter(pk__in=articles_ids)
    page_obj, sorted_articles = sort_and_paginate(articles, page)
    trigrams_dict = build_pagination_hints(sorted_articles, num_by_page)

    return Content(page_obj=page_obj, trigrams_dict=trigrams_dict)
