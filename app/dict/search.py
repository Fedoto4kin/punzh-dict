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
    ArticleIndexTranslate,
    ArticleIndexWord,
    ArticleIndexWordNormalization,
    ArticleIndexTag,
    Tag,
    ArticleLink,
    ArticleSemanticField,
    SemanticField,
    Levenshtein,
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
_FUZZY_SUFFIX = r"[а-яё]{1,3}"

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


def _display_label(phrase, query_words):
    """Narrowing tag label: drop exact query tokens, keep punctuation (e.g. скобки)."""
    label = phrase
    for qw in sorted(query_words, key=len, reverse=True):
        label = re.sub(
            r"(?<![а-яё])" + re.escape(qw) + r"(?![а-яё])",
            "",
            label,
            flags=re.IGNORECASE,
        )
    label = re.sub(r"\s+", " ", label).strip()
    label = re.sub(r"\(\s+", "(", label)
    label = re.sub(r"\s+\)", ")", label)
    label = label.strip(" ,")
    return label or phrase


def _label_and_key_tokens(phrase, query_words, stopwords):
    toks = _TOKEN_RE.findall(phrase.lower())
    label_toks = [t for t in toks if t not in query_words]  # drop the query's own words
    key_toks = [t for t in label_toks if t not in stopwords]
    return label_toks, key_toks


def split_by_coverage(candidates, page_blobs, query_words, stopwords):
    """
    Classify suggestion phrases into narrowing tags relative to the anchor's
    result set. No "similar" class (SPEC v2 §0, §2): candidates come from the
    anchor's own full-text hits, so every key is inside the result set.

    candidates : suggestion phrases (rus_word), e.g. "быстро ехать".
    page_blobs : per-card joined lowercase translations of the result set.
    query_words: set of the query's own tokens, dropped from label and key by
                 EXACT match. NOTE: morphological variants of the query
                 (e.g. "быстрее" when the query is "быстро") are NOT removed —
                 they leak into the label. Accepted for now; a stemmer would
                 fix it (SPEC v2, deferred).
    stopwords  : tokens dropped from the KEY only (kept in the label).

    LABEL = candidate minus query words (stopwords kept) -> shown.
    KEY   = label minus stopwords -> matched.
    COVERAGE = cards whose blob contains at least one key token as a substring.
      0 < coverage < N -> narrowing;  coverage in {0, N} or empty key -> dropped.

    Returns narrowing: [{"label","key","coverage"}], deduped by key
    (first label wins), sorted by ascending coverage.
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

        coverage = sum(1 for b in blobs if any(t in b for t in key_toks))
        if coverage == 0 or coverage == N:
            continue

        narrowing.append(
            {
                "label": _display_label(phrase, query_words),
                "key": key,
                "coverage": coverage,
            }
        )

    narrowing.sort(key=lambda e: e["coverage"])

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


def search_by_translate_linked(query: str, page=1, f=None):

    # 1. ILIKE (exact rus_word match, case-insensitive; query already ё→е in views)
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
    all_ids = list(ids_ilike | token_match_ids)

    # 4. Расширяем через связи ArticleLink
    expanded_ids = expand_by_links(all_ids)

    # 5. Кандидаты для сужающих тегов (SPEC v2, механизм 1)
    candidate_article_ids = expanded_ids
    if query.strip().lower() in HIGH_FREQ_ANCHOR_QUERIES:
        candidate_article_ids = ids_ilike
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
        # f — ключ уточняющего тега: оставить карточки, чей перевод содержит
        # ЛЮБОЙ токен ключа (то же правило, что считало coverage).
        f_tokens = _TOKEN_RE.findall(f.lower())
        kept = set()
        for aid, rus_words in blobs_by_article.items():
            blob = " | ".join(rus_words).lower()
            for tok in f_tokens:
                if tok in blob:
                    kept.add(aid)
                    break
        filtered_ids = set(result_ids) & kept

    page_obj, found_count = get_sorted_articles(filtered_ids, page)

    return page_obj, found_count, narrowing, direct_ids, related_queries


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


def word_search(query: str, page: int) -> Paginator:
    return get_sorted_articles(krl_article_ids(query), page)


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
