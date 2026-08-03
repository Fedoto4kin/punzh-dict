import re
from dataclasses import dataclass
from itertools import chain

from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
    TrigramSimilarity,
)
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.db.models.functions import Length

from .helpers import build_pagination_hints, normalization, sorted_by_krl
from .models import (
    Article,
    ArticleAddition,
    ArticleIndexTranslate,
    ArticleIndexWord,
    ArticleIndexWordNormalization,
    ArticleIndexTag,
    Tag,
    ArticleLink,
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
    Возвращает множество статей, связанных с article_ids
    в обе стороны.
    """
    outgoing = ArticleLink.objects.filter(from_article_id__in=article_ids).values_list(
        "to_article_id", flat=True
    )

    incoming = ArticleLink.objects.filter(to_article_id__in=article_ids).values_list(
        "from_article_id", flat=True
    )

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
    "в", "с", "на", "и", "из", "по", "от", "к", "со", "о", "за", "до", "во",
    "не", "у", "то", "же", "ее", "ни", "да", "но", "ко", "а", "бы", "ли",
    "их", "им", "та", "вы", "об", "ле", "те", "он", "мы",
}
_STOP_1B = {
    "что-л", "чем-л", "чего-л", "кого-л", "чему-л", "куда-л", "кем-л",
    "где-л", "кому-л", "какое-л", "какого-л", "каком-л", "откуда-л",
    "каким-л", "какую-л", "каких-л", "какой-л", "какие-л", "чью-л",
    "чьего-л", "какая-л",
}
STOPWORDS = _STOP_1A | _STOP_1B


def _label_and_key_tokens(phrase, query_words, stopwords):
    toks = _TOKEN_RE.findall(phrase.lower())
    label_toks = [t for t in toks if t not in query_words]   # drop the query's own words
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
            {"label": " ".join(label_toks), "key": key, "coverage": coverage}
        )

    narrowing.sort(key=lambda e: e["coverage"])

    return narrowing


def find_direct_hits(blobs_by_article, result_ids, links):
    """
    Direct hits (SPEC v2). An article qualifies two ways:
      * base: every rus_word entry is a single token, no phrase (ruttoh ->
        быстро, круто, скоро);
      * inherited: it has NO translations of its own but is linked (either
        direction) to at least one BASE direct hit (rutoldi -> "см. ruttoh").
        Inheritance is ONE hop from a base direct hit only.

    blobs_by_article: {article_id: [rus_word, ...]} for articles that have
                      translations (empty-list keys count as no translation).
    result_ids      : the full result set (ids).
    links           : {article_id: set(neighbour_ids)} within the result set.

    Returns set(article_id).
    """
    base_direct = set()
    for aid, rus_words in blobs_by_article.items():
        if not rus_words:
            continue
        all_single = True
        for rw in rus_words:
            if len(_TOKEN_RE.findall(rw.lower())) > 1:
                all_single = False
                break
        if all_single:
            base_direct.add(aid)

    translationless = set(result_ids) - set(blobs_by_article.keys())
    inherited = set()
    for aid in translationless:
        if links.get(aid, set()) & base_direct:
            inherited.add(aid)

    return base_direct | inherited


def search_by_translate_linked(query: str, page=1, f=None):

    # 1. ILIKE
    ids_ilike = ArticleIndexTranslate.objects.filter(rus_word__ilike=query).values_list(
        "article_id", flat=True
    )

    # 2. Fulltext
    words = query.split()
    search_query = SearchQuery(words[0], config="russian")
    for word in words[1:]:
        search_query |= SearchQuery(word, config="russian")

    search_vector = SearchVector("rus_word", config="russian")

    fulltext_results = (
        ArticleIndexTranslate.objects.annotate(
            rank=SearchRank(search_vector, search_query)
        )
        .filter(rank__gte=0.01)
        .order_by("-rank")
    )

    fulltext_ids = fulltext_results.values_list("article_id", flat=True)
    fulltext_ids = set(fulltext_ids) - set(ids_ilike)

    # 3. Объединяем
    all_ids = list(set(chain(ids_ilike, fulltext_ids)))

    # 4. Расширяем через связи ArticleLink
    expanded_ids = expand_by_links(all_ids)

    # 5. Кандидаты для сужающих тегов (SPEC v2, механизм 1)
    candidates = list(
        fulltext_results.filter(article_id__in=expanded_ids)
        .values_list("rus_word", flat=True)
        .distinct()
    )

    # Множество, реально попавшее в выдачу
    result_ids = expanded_ids if expanded_ids else set(ids_ilike)

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

    # Связи внутри выдачи (обе стороны) — для наследования "прямых" попаданий
    links = {}
    for fa, ta in ArticleLink.objects.filter(
        from_article_id__in=result_ids, to_article_id__in=result_ids
    ).values_list("from_article_id", "to_article_id"):
        links.setdefault(fa, set()).add(ta)
        links.setdefault(ta, set()).add(fa)
    direct_ids = find_direct_hits(blobs_by_article, result_ids, links)

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

    return page_obj, found_count, narrowing, direct_ids


# ------------------------------------------------------------
#  Поиск по карельскому слову
# ------------------------------------------------------------


def word_search(query: str, page: int) -> Paginator:
    ids = ArticleIndexWord.objects.filter(word__ilike=query).values_list(
        "article_id", flat=True
    )

    return get_sorted_articles(ids, page)


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
    sel_types = dict(
        Tag.objects.filter(id__in=selected).values_list("id", "type")
    )
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
