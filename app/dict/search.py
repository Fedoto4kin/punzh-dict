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


def _label_and_key_tokens(phrase, anchor_stem, stopwords):
    toks = _TOKEN_RE.findall(phrase.lower())
    label_toks = [t for t in toks if not t.startswith(anchor_stem)]
    key_toks = [t for t in label_toks if t not in stopwords]
    return label_toks, key_toks


def split_by_coverage(candidates, page_blobs, anchor_stem, stopwords):
    """
    Classify suggestion phrases into narrowing tags relative to the anchor's
    result set. There is no "similar" class: candidates come from the anchor's
    own full-text hits, so every key is already inside the result set
    (coverage >= 1). Similar/semantic neighbours are a separate mechanism
    (fuzzy rescue / pgvector), not this function. See SPEC v2 §2, §0.

    candidates : list of suggestion phrases (rus_word), e.g. "быстро ехать".
    page_blobs : per-card joined lowercase translations of the anchor result
                 set; N = len(page_blobs).
    anchor_stem: stem of the anchor query; tokens starting with it are dropped
                 from both label and key (e.g. "быстр").
    stopwords  : set of tokens dropped from the KEY only (kept in the label).

    LABEL = candidate minus anchor tokens (stopwords kept) -> what we show.
    KEY   = label minus stopwords -> what we match on.
    COVERAGE = number of cards whose blob contains at least one key token
               as a substring.

        0 < coverage < N  -> narrowing tag
        coverage == N      -> dropped (covers everything == the anchor)
        coverage == 0      -> dropped (unreachable from this source; a jump
                                       out is served elsewhere)
        empty key          -> dropped (nothing left to match on)

    Returns narrowing: [{"label","key","coverage"}], deduped by key (first
    label wins), sorted by ascending coverage.
    """
    blobs = [b.lower() for b in page_blobs]
    N = len(blobs)

    seen_keys = set()
    narrowing = []

    for phrase in candidates:
        label_toks, key_toks = _label_and_key_tokens(phrase, anchor_stem, stopwords)
        if not key_toks:
            continue                                  # empty key -> drop
        key = " ".join(key_toks)
        if key in seen_keys:
            continue                                  # dedup by key
        seen_keys.add(key)

        coverage = sum(1 for b in blobs if any(t in b for t in key_toks))
        if coverage == 0 or coverage == N:
            continue                                  # nothing to narrow -> drop

        narrowing.append(
            {"label": " ".join(label_toks), "key": key, "coverage": coverage}
        )

    narrowing.sort(key=lambda e: e["coverage"])
    return narrowing

def search_by_translate_linked(query: str, page=1):

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

    # 5. Для блока "возможно..."
    possible_translations = (
        fulltext_results.filter(article_id__in=expanded_ids)
        .values("rus_word")
        .distinct()
    )

    # Если найдено хотя бы одно слово из пространства связей — выводим весь кластер
    if expanded_ids:
        page_obj, found_count = get_sorted_articles(expanded_ids, page)
    else:
        page_obj, found_count = get_sorted_articles(ids_ilike, page)

    return page_obj, found_count, list(possible_translations)


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


def search_by_tags_smart(
    by_geo: [], by_tags: [], by_ling: [], by_dialect: [], by_other: [], page: int
) -> Content:

    def search_by_ids(ids: [], articles_ids: [], i=True) -> []:

        tags = Tag.objects.filter(id__in=ids).values_list("tag", flat=True)
        if i:
            queries = [
                Q(article_html__contains="<i>" + value + "</i>")
                | Q(additions__article_html__contains="<i>" + value + "</i>")
                for value in tags
            ]
        else:
            queries = [
                Q(article_html__contains=value)
                | Q(additions__article_html__contains=value)
                for value in tags
            ]
        query = queries.pop()
        for item in queries:
            query |= item
        articles_with_tags = Article.objects.filter(query).values_list("id", flat=True)
        found_articles = list(set(articles_with_tags) & set(articles_ids))
        return list(set(found_articles) & set(articles_ids))

    articles_ids = Article.objects.all().values_list("id", flat=True)

    if len(by_geo):
        articles_ids = search_by_ids(by_geo, articles_ids)
    if len(by_ling):
        articles_ids = search_by_ids(by_ling, articles_ids)
    if len(by_tags):
        articles_ids = search_by_ids(by_tags, articles_ids)
    if len(by_dialect):
        articles_ids = search_by_ids(by_dialect, articles_ids)
    if len(by_other):
        articles_ids = search_by_ids(by_other, articles_ids, False)

    articles = Article.objects.filter(pk__in=articles_ids)
    page_obj, sorted_articles = sort_and_paginate(articles, page)

    trigrams_dict = build_pagination_hints(sorted_articles, num_by_page)

    return Content(page_obj=page_obj, trigrams_dict=trigrams_dict)


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
