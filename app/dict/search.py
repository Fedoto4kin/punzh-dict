import re
from dataclasses import dataclass

from django.contrib.postgres.search import TrigramSimilarity
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.db.models.functions import Length

from .helpers import (
    build_pagination_hints,
    fold_interior_hyphens,
    normalization,
    sorted_by_krl,
)
from .models import (
    Article,
    ArticleAddition,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleIndexWord,
    ArticleIndexWordNormalization,
    ArticleLink,
    ArticleSemanticField,
    Levenshtein,
    SemanticField,
    Tag,
)

num_by_page = 18


@dataclass
class Content:
    """Container returned by the listing/search views."""

    page_obj: object = None
    last_page_word: str = ""
    first_page_word: str = ""
    trigrams_dict: object = None


# ------------------------------------------------------------
#  Общий примитив: карельская сортировка + пагинация
# ------------------------------------------------------------


def sort_and_paginate(articles, page):
    """
    Karelian-collated in-memory sort + pagination, shared by every listing
    view. `articles` is a filtered Article queryset (or any iterable); the
    caller passes it already filtered and prefetched as needed.

    Sorting must run in Python: sorted_by_krl relies on normalization(),
    which is regex-based and cannot be expressed in SQL. The input keeps its
    default DB ordering ("word"), so ties in the collation key resolve exactly
    as before via Python's stable sort.

    Returns (page_obj, sorted_articles); the sorted list is reused by callers
    for build_pagination_hints.
    """
    sorted_articles = sorted(articles, key=lambda el: sorted_by_krl(el, "word"))
    paginator = Paginator(sorted_articles, num_by_page)
    return paginator.get_page(page), sorted_articles


# ------------------------------------------------------------
#  Расширение списка статей через связи ArticleLink
# ------------------------------------------------------------


def expand_by_links(article_ids):
    """
    Кластер по направленным ArticleLink (см. и от, обе стороны; без ср.).
    """
    kinds = ArticleLink.KINDS_LISTING
    outgoing = ArticleLink.objects.filter(
        from_article_id__in=article_ids, kind__in=kinds
    ).values_list("to_article_id", flat=True)

    incoming = ArticleLink.objects.filter(
        to_article_id__in=article_ids, kind__in=kinds
    ).values_list("from_article_id", flat=True)

    return set(article_ids) | set(outgoing) | set(incoming)


# ------------------------------------------------------------
#  Поиск по букве
# ------------------------------------------------------------


def search_by_pointer(letter: str, page: int) -> Content:

    articles = Article.objects.filter(first_letter=letter.upper())
    page_obj, sorted_articles = sort_and_paginate(articles, page)

    trigrams_dict = build_pagination_hints(sorted_articles, num_by_page)

    last_page_word = ""
    first_page_word = ""
    if len(page_obj):
        last_page_word = normalization(page_obj[-1].word)
        first_page_word = normalization(page_obj[0].word)

    return Content(
        page_obj=page_obj,
        last_page_word=last_page_word,
        first_page_word=first_page_word,
        trigrams_dict=trigrams_dict,
    )


# ------------------------------------------------------------
#  Общий метод сортировки + пагинации
# ------------------------------------------------------------


def get_sorted_articles(ids: [], page: int) -> Paginator:
    articles = Article.objects.prefetch_related("additions").filter(pk__in=ids)
    page_obj, _ = sort_and_paginate(articles, page)

    return page_obj, page_obj.paginator.count


# ------------------------------------------------------------
#  Поиск по русскому переводу
# ------------------------------------------------------------

_TOKEN_RE = re.compile(r"[а-яё\-]+", re.IGNORECASE)

# Stop-words for the narrowing split (SPEC v2 §5): corpus buckets 1a (len<=2)
# and 1b (dictionary abbreviations ending in -л). Static list.
_STOP_1A = {
    "в",
    "с",
    "на",
    "и",
    "из",
    "по",
    "от",
    "к",
    "со",
    "о",
    "за",
    "до",
    "во",
    "не",
    "у",
    "то",
    "же",
    "ее",
    "ни",
    "да",
    "но",
    "ко",
    "а",
    "бы",
    "ли",
    "их",
    "им",
    "та",
    "вы",
    "об",
    "ле",
    "те",
    "он",
    "мы",
}
_STOP_1B = {
    "что-л",
    "чем-л",
    "чего-л",
    "кого-л",
    "чему-л",
    "куда-л",
    "кем-л",
    "где-л",
    "кому-л",
    "какое-л",
    "какого-л",
    "каком-л",
    "откуда-л",
    "каким-л",
    "какую-л",
    "каких-л",
    "какой-л",
    "какие-л",
    "чью-л",
    "чьего-л",
    "какая-л",
}
STOPWORDS = _STOP_1A | _STOP_1B

# Anchor queries where token-OR hits are huge: narrowing candidates only from
# ILIKE-exact articles (backlog §2 prio-filter «быть»).
HIGH_FREQ_ANCHOR_QUERIES = frozenset({"быть"})

# Short-prefix fuzzy token match (backlog P3 surrogate): «корова» → «корове».
_FUZZY_TOKEN_MIN_LEN = 5
# One inflection letter (корова/корове); not derivational siblings (понизу/понизить).
_FUZZY_SUFFIX = r"[а-яё]"

# Token boundary for rus_word: same alphabet as _TOKEN_RE ([а-яё\-] tokens).
_TOKEN_BOUNDARY_BEFORE = r"(?:^|[^а-яё\-])"
_TOKEN_BOUNDARY_AFTER = r"(?:$|[^а-яё\-])"


def _query_tokens(query):
    return _TOKEN_RE.findall(query.lower())


def _token_boundary_regex(token):
    return _TOKEN_BOUNDARY_BEFORE + re.escape(token) + _TOKEN_BOUNDARY_AFTER


def _token_boundary_fuzzy_regex(token):
    """Stem = token minus last letter; matches inflection variants (корова/корове)."""
    stem = token[:-1]
    return (
        _TOKEN_BOUNDARY_BEFORE + re.escape(stem) + _FUZZY_SUFFIX + _TOKEN_BOUNDARY_AFTER
    )


def _translate_q_any_query_token(query_tokens):
    """OR: rus_word contains at least one query token as a whole word."""
    combined = Q()
    for tok in query_tokens:
        combined |= Q(rus_word__iregex=_token_boundary_regex(tok))
        if len(tok) >= _FUZZY_TOKEN_MIN_LEN:
            combined |= Q(rus_word__iregex=_token_boundary_fuzzy_regex(tok))
    return combined


def _strip_parens_for_key(phrase):
    """Parenthetical glosses (о корове), (детс.) — excluded from key unless head is only the query."""
    return re.sub(r"\([^)]*\)", " ", phrase)


def _paren_gloss_tokens(phrase):
    """Lowercase tokens taken from (…) segments."""
    gloss = " ".join(re.findall(r"\(([^)]*)\)", phrase))
    if not gloss:
        return []
    return _TOKEN_RE.findall(gloss.lower())


def _label_and_key_tokens(phrase, query_words, stopwords):
    key_source = _strip_parens_for_key(phrase)
    toks = _TOKEN_RE.findall(key_source.lower())
    label_toks = [t for t in toks if t not in query_words]
    key_toks = [t for t in label_toks if t not in stopwords]
    if not key_toks:
        # «случаться (о домашних животных)»: distinguisher lives only in parens.
        paren_toks = _paren_gloss_tokens(phrase)
        key_toks = [
            t for t in paren_toks if t not in query_words and t not in stopwords
        ]
    return label_toks, key_toks


def _blob_matches_key_tokens(blob, key_tokens):
    """All key tokens must appear in the blob (substring, same as ?f= filter)."""
    if not key_tokens:
        return False
    return all(tok in blob for tok in key_tokens)


def split_by_coverage(candidates, page_blobs, query_words, stopwords):
    """
    Classify suggestion phrases into narrowing tags relative to the anchor's
    result set. No "similar" class (SPEC v2 §0, §2): candidates come from the
    anchor's own full-text hits, so every key is inside the result set.

    candidates : suggestion phrases (rus_word), e.g. "быстро ехать".
    page_blobs : per-card joined lowercase translations of the result set.
    query_words: set of the query's own tokens, dropped from KEY by EXACT match.
    stopwords  : tokens dropped from the KEY only (kept in the label).

    LABEL = full candidate phrase (shown on the button).
    KEY   = phrase minus parens, query words, stopwords -> matched by ?f= (AND).
      If that yields an empty key, tokens from (…) are used instead
      («случаться (о домашних животных)» -> key «домашних животных»).
    COVERAGE = cards whose blob contains every key token as a substring.
      0 < coverage < N -> narrowing;  coverage in {0, N} or empty key -> dropped.

    Returns narrowing: [{"label","key","coverage"}], deduped by key
    (first label wins), sorted by descending coverage (broader tags first),
    then by label for ties.
    """
    blobs = [b.lower() for b in page_blobs]
    N = len(blobs)

    seen_keys = set()
    narrowing = []

    for phrase in candidates:
        label_toks, key_toks = _label_and_key_tokens(phrase, query_words, stopwords)
        if not key_toks:
            continue
        key = " ".join(key_toks)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        coverage = sum(1 for b in blobs if _blob_matches_key_tokens(b, key_toks))
        if coverage == 0 or coverage == N:
            continue

        narrowing.append({"label": phrase, "key": key, "coverage": coverage})

    narrowing.sort(key=lambda e: (-e["coverage"], e["label"]))

    return narrowing


def find_exact_match_ids(result_ids, ilike_ids, blobs_by_article, links):
    """
    Exact matches for ?f=exact (query-normalized ILIKE on rus_word):
      * article has at least one rus_word equal to the query (ilike_ids);
      * inherited: no translations of its own, linked (either direction,
        one hop within result_ids) to such an ILIKE hit (rutoldi -> «см. ruttoh»).

    Link-expanded articles that have their own translations but no exact
    rus_word match are excluded (e.g. ehatta with only «быстро ехать»).
    """
    ilike_in_result = set(ilike_ids) & set(result_ids)
    translationless = set(result_ids) - set(blobs_by_article.keys())
    inherited = {
        aid for aid in translationless if links.get(aid, set()) & ilike_in_result
    }
    return ilike_in_result | inherited


def find_related_queries(ilike_ids, blobs_by_article, query_words):
    """
    One-word rus_word synonyms from articles with a direct ILIKE hit on the query.
    Other single-token translations of the same card, minus query tokens; deduped.
    """
    seen = set()
    related = []
    for aid in ilike_ids:
        for rw in blobs_by_article.get(aid, []):
            if not rw:
                continue
            toks = _TOKEN_RE.findall(rw.lower())
            if len(toks) != 1:
                continue
            tok = toks[0]
            if tok in query_words or tok in seen:
                continue
            seen.add(tok)
            related.append(tok)
    related.sort()
    return related


@dataclass
class RusSearchCore:
    """Intermediate sets for the Russian search pipeline (public + debug)."""

    query: str
    query_tokens: list
    ids_ilike: set
    token_match_ids: set
    seed_ids: set
    expanded_ids: set
    result_ids: set
    blobs_by_article: dict
    links: dict
    narrowing: list
    direct_ids: set
    related_queries: list
    filtered_ids: set
    f: object
    high_freq_anchor: bool
    candidates: list


def rus_search_core(query: str, f=None) -> RusSearchCore:
    """
    Full Russian lexical pipeline without pagination.
    `query` must already be ё→е normalized (as in views.search).
    """
    # 1. ILIKE (exact rus_word match, case-insensitive)
    ids_ilike = set(
        ArticleIndexTranslate.objects.filter(rus_word__ilike=query).values_list(
            "article_id", flat=True
        )
    )

    # 2. Token match (OR): any query token as a whole word in rus_word (no stemmer).
    query_tokens = _query_tokens(query)
    token_q = _translate_q_any_query_token(query_tokens) if query_tokens else Q(pk=-1)

    token_match_ids = (
        set(
            ArticleIndexTranslate.objects.filter(token_q).values_list(
                "article_id", flat=True
            )
        )
        - ids_ilike
    )

    # 3. Объединяем
    seed_ids = ids_ilike | token_match_ids
    all_ids = list(seed_ids)

    # 4. Расширяем через связи ArticleLink
    expanded_ids = expand_by_links(all_ids)

    # 5. Кандидаты для сужающих тегов (SPEC v2, механизм 1)
    high_freq_anchor = query.strip().lower() in HIGH_FREQ_ANCHOR_QUERIES
    candidate_article_ids = ids_ilike if high_freq_anchor else expanded_ids
    candidates = list(
        ArticleIndexTranslate.objects.filter(
            token_q, article_id__in=candidate_article_ids
        )
        .values_list("rus_word", flat=True)
        .distinct()
    )

    # Множество, реально попавшее в выдачу
    result_ids = expanded_ids if expanded_ids else ids_ilike

    # page_blobs: переводы по каждой карточке выдачи, ОДНИМ запросом
    blobs_by_article = {}
    for aid, rus_word in ArticleIndexTranslate.objects.filter(
        article_id__in=result_ids
    ).values_list("article_id", "rus_word"):
        if rus_word:
            blobs_by_article.setdefault(aid, []).append(rus_word)
    page_blobs = [" | ".join(v) for v in blobs_by_article.values()]

    query_words = set(_TOKEN_RE.findall(query.lower()))
    narrowing = split_by_coverage(candidates, page_blobs, query_words, STOPWORDS)

    # Связи внутри выдачи (обе стороны) — для наследования точных попаданий
    links = {}
    for fa, ta in ArticleLink.objects.filter(
        from_article_id__in=result_ids,
        to_article_id__in=result_ids,
        kind__in=ArticleLink.KINDS_LISTING,
    ).values_list("from_article_id", "to_article_id"):
        links.setdefault(fa, set()).add(ta)
        links.setdefault(ta, set()).add(fa)
    direct_ids = find_exact_match_ids(result_ids, ids_ilike, blobs_by_article, links)
    related_queries = find_related_queries(ids_ilike, blobs_by_article, query_words)

    # Фильтр применяется ПОСЛЕ вычисления тегов/прямых (они всегда от полного
    # якоря) и ДО пагинации, чтобы номера страниц и n-граммы совпадали с
    # отфильтрованным набором.
    filtered_ids = result_ids
    if f == "exact":
        filtered_ids = set(result_ids) & direct_ids
    elif f:
        # f — ключ тега: все токены ключа должны быть в блобе переводов (AND).
        f_tokens = _TOKEN_RE.findall(f.lower())
        kept = set()
        for aid, rus_words in blobs_by_article.items():
            blob = " | ".join(rus_words).lower()
            if _blob_matches_key_tokens(blob, f_tokens):
                kept.add(aid)
        filtered_ids = set(result_ids) & kept

    return RusSearchCore(
        query=query,
        query_tokens=query_tokens,
        ids_ilike=ids_ilike,
        token_match_ids=token_match_ids,
        seed_ids=seed_ids,
        expanded_ids=expanded_ids,
        result_ids=result_ids,
        blobs_by_article=blobs_by_article,
        links=links,
        narrowing=narrowing,
        direct_ids=direct_ids,
        related_queries=related_queries,
        filtered_ids=filtered_ids,
        f=f,
        high_freq_anchor=high_freq_anchor,
        candidates=candidates,
    )


def search_by_translate_linked(query: str, page=1, f=None):
    core = rus_search_core(query, f=f)
    page_obj, found_count = get_sorted_articles(core.filtered_ids, page)
    return (
        page_obj,
        found_count,
        core.narrowing,
        core.direct_ids,
        core.related_queries,
    )


# ------------------------------------------------------------
#  Поиск по карельскому слову
# ------------------------------------------------------------


# Same mapping the public search form applies before ILIKE: '.' is one
# character, '?' is any sequence; sibilants and ü/y fold like the word index.
_KRL_ILIKE_TRANS = str.maketrans(
    {
        ";": "",
        "’": "",
        "'": "",
        "ʼ": "",
        ",": "",
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
    return fold_interior_hyphens(query.translate(_KRL_ILIKE_TRANS))


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


def format_krl_filter_query(tag_ids, phrase=False):
    """GET suffix: '', '?t=1,2', '?ph=1', or '?t=1,2&ph=1'."""
    parts = []
    if tag_ids:
        parts.append("t=" + ",".join(str(i) for i in tag_ids))
    if phrase:
        parts.append("ph=1")
    return ("?" + "&".join(parts)) if parts else ""


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


def word_search(query: str, page: int, tag_ids=None, phrase=False):
    """
    Karelian headword search, optional ?t= / ?ph= filters.

    Returns (page_obj, found_count, tag_filter_groups, phrase_filter, t_query).
    """
    base_ids = set(krl_article_ids(query))
    selected = normalize_krl_tag_ids(tag_ids or [])
    phrase = bool(phrase)
    filtered_ids = _apply_krl_filters(base_ids, selected, phrase)
    page_obj, found_count = get_sorted_articles(filtered_ids, page)
    groups, phrase_filter = krl_tag_facets(base_ids, selected, phrase)
    return (
        page_obj,
        found_count,
        groups,
        phrase_filter,
        format_krl_filter_query(selected, phrase),
    )


# ------------------------------------------------------------
#  Поиск возможных слов
# ------------------------------------------------------------


def search_possible(query: str) -> set:

    def search_levenshtein(query: str):
        return (
            ArticleIndexWordNormalization.objects.annotate(
                lev_dist=Levenshtein(F("word"), query)
            )
            .filter(lev_dist__lte=2)
            .order_by("-lev_dist", Length("word").asc())
        )

    def search_trigram(query: str):
        return (
            ArticleIndexWordNormalization.objects.annotate(
                similarity=TrigramSimilarity("word", query),
            )
            .filter(similarity__gt=0.2)
            .order_by("-similarity", Length("word").asc())
        )

    return set(
        w.word
        for w in (
            set(search_trigram(query.lower())) & set(search_levenshtein(query.lower()))
        )
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


def article_ids_for_semantic_field(field_id):
    """
    Articles in a semantic field, plus unmarked «см.» referrers.

    Lemmas classified into the field are the core set. Articles that only
    point at those lemmas via ArticleLink (см. / от, no translation for the
    LLM to tag) inherit the field at read time — same kinds as
    expand_by_links in Russian search, but one-way: we do not follow
    outgoing links, which would leak unrelated targets into the listing.
    Referrers that already have any semantic field keep their own markup.
    """
    classified = set(
        ArticleSemanticField.objects.filter(field_id=field_id).values_list(
            "article_id", flat=True
        )
    )
    if not classified:
        return classified
    referrers = set(
        ArticleLink.objects.filter(
            to_article_id__in=classified,
            kind__in=ArticleLink.KINDS_LISTING,
        ).values_list("from_article_id", flat=True)
    )
    if not referrers:
        return classified
    marked = set(
        ArticleSemanticField.objects.filter(article_id__in=referrers).values_list(
            "article_id", flat=True
        )
    )
    return classified | (referrers - marked)


def semantic_fields_with_counts():
    fields = list(SemanticField.objects.all())
    for field in fields:
        field.article_count = len(article_ids_for_semantic_field(field.pk))
    return fields


def search_by_semantic_field(field_id, page):
    articles = Article.objects.filter(
        pk__in=article_ids_for_semantic_field(field_id)
    ).prefetch_related("additions")
    page_obj, sorted_articles = sort_and_paginate(articles, page)
    trigrams_dict = build_pagination_hints(sorted_articles, num_by_page)
    return Content(page_obj=page_obj, trigrams_dict=trigrams_dict)


# ------------------------------------------------------------
#  Определение направления поиска в словаре
# ------------------------------------------------------------


def detect_direction(query: str) -> str:
    """
    Decide the search direction from the query text.

    A query is Russian ('rus') if it contains any Cyrillic letter; otherwise
    it is Karelian ('krl'), which is written in Latin script with diacritics.
    Cyrillic presence anywhere is the signal — not the first character, and
    punctuation/whitespace (including the '.'/'?' fuzzy-search syntax) never
    affects the choice.
    """
    if re.search(r"[а-яё]", query, re.IGNORECASE):
        return "rus"
    return "krl"
