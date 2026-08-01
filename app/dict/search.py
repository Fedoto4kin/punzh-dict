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
