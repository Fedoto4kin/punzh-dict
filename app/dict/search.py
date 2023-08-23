from django.contrib.postgres.search import TrigramSimilarity
from django.db.models.functions import Length
from django.core.paginator import Paginator
from django.db.models import F, Q
from itertools import chain

from .helpers import sorted_by_krl
from .models import *

num_by_page = 18


def search_by_pointer(letter: str, page: int) -> object:

    last_page_word = ''
    first_page_word = ''
    trigrams_dict = {}

    articles = sorted(Article.objects.all().filter(first_letter=letter.upper()),
                      key=lambda el: (
                          sorted_by_krl(el, 'word')
                      )
                      )

    paginator = Paginator(articles, num_by_page)
    page_obj = paginator.get_page(page)

    ngrams = trigrams = [create_ngram(a.word, 3) for a in articles[0::num_by_page]]

    for idx in range(1, len(trigrams)-1):
        n = 3
        while True:
            if n > len(articles[0::num_by_page][idx].word):
                break
            prev_ng = create_ngram(articles[0::num_by_page][idx-1].word, n)
            next_ng = create_ngram(articles[0::num_by_page][idx+1].word, n)
            ngrams[idx] = create_ngram(articles[0::num_by_page][idx].word, n)

            if ngrams[idx][0:n] != prev_ng and ngrams[idx][0:n] != next_ng:
                break
            n += 1

    for idx in range(0, len(ngrams)-1):
        if idx+1 <= len(ngrams):
            ngrams[idx] = ngrams[idx] + ' ·· ' + ngrams[idx+1]


    if len(page_obj):
        last_page_word = normalization(page_obj[-1].word)
        first_page_word = normalization(page_obj[0].word)
        trigrams_dict = dict(
            zip(
                range(1, len(trigrams) + 1),
                ngrams
            )
        )
    return type('Content', (object,),
                {
                    'page_obj': page_obj,
                    'last_page_word': last_page_word,
                    'first_page_word': first_page_word,
                    'trigrams_dict': trigrams_dict
                })()


def get_sorted_articles(ids: [], page: int) -> Paginator:

    articles = sorted(Article.objects.prefetch_related('additions').extra(select={'sort_order': "0"}).filter(pk__in=ids).all(),
                      key=lambda el: (
                          sorted_by_krl(el, 'word'),
                      )
                      )

    paginator = Paginator(articles, num_by_page)
    return paginator.get_page(page)


def search_by_translate_linked(query: str, page=1) -> Paginator:

    query = query.replace('ё', 'е') \
        .replace('?', '%') \
        .replace('.', '_')
    print(query)
    ids = ArticleIndexTranslate.objects.filter(rus_word__ilike=query).values_list('article_id', flat=True)
    linked_ids = Article.objects.filter(linked_article__in=ids).values_list('id', flat=True)
    return get_sorted_articles(list(chain(linked_ids, ids)), page)


def search_by_translate(query: str, page=1) -> Paginator:

    query = query.replace('ё', 'е')
    ids = ArticleIndexTranslate.objects.filter(rus_word__istartswith=query).values_list('article_id', flat=True)

    return get_sorted_articles(ids, page)


def word_search(query: str, page: int) -> Paginator:

    query = query.replace('š', 's') \
        .replace('č', 'c') \
        .replace('ž', 'z') \
        .replace('?', '%') \
        .replace('.', '_')

    ids = ArticleIndexWord.objects.filter(word__ilike=query).values_list('article_id', flat=True)
    return get_sorted_articles(ids, page)


def search_possible(query: str) -> set:
    return set(w.word for w in (set(search_trigram(query.lower())) & set(search_levenshtein(query.lower()))))


def search_trigram(query: str):

    return ArticleIndexWordNormalization.objects.annotate(similarity=TrigramSimilarity('word', query), ) \
        .filter(similarity__gt=0.2) \
        .order_by('-similarity', Length('word').asc())


def search_levenshtein(query: str):

    return ArticleIndexWordNormalization.objects.annotate(
        lev_dist=Levenshtein(F('word'), query)
    ).filter(
        lev_dist__lte=2
    ) \
        .order_by('-lev_dist', Length('word').asc())


def get_tags_by_type(type_id=None) -> set:
    if type_id:
        return Tag.objects.filter(type=type_id).order_by('sorting', 'name')
    return Tag.objects.all()


def get_tags_by_ids_distinct(ids: []) -> set:
    return set(Tag.objects.filter(id__in=ids).values_list('name', flat=True))


def search_by_tags_smart(by_geo: [],
                         by_tags: [],
                         by_ling: [],
                         by_dialect: [],
                         by_other: [],
                         page: int) -> object:

    def search_by_ids(ids: [], articles_ids: [], i=True) -> []:

        tags = Tag.objects.filter(id__in=ids).values_list('tag', flat=True)
        if i:
            queries = [
                Q(article_html__contains='<i>' + value + '</i>')
                | Q(additions__article_html__contains='<i>' + value + '</i>')
                for value in tags
            ]
        else:
            queries = [
                Q(article_html__contains=value)
                | Q(additions__article_html__contains=value)
                for value in tags
            ]
        # Take one Q object from the list
        query = queries.pop()
        # Or the Q object with the ones remaining in the list
        for item in queries:
            query |= item
        articles_with_tags = Article.objects \
            .filter(query) \
            .values_list('id', flat=True)
        found_articles = list(set(articles_with_tags) & set(articles_ids))
        return list(set(found_articles) & set(articles_ids))

    articles_ids = Article.objects \
        .all() \
        .values_list('id', flat=True)
    trigrams_dict = None

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

    articles = sorted(Article.objects.extra(select={'sort_order': "0"}).filter(pk__in=articles_ids).all(),
                      key=lambda el: (
                          sorted_by_krl(el, 'word'),
                      )
                      )
    # todo: make common method
    paginator = Paginator(articles, num_by_page)
    page_obj = paginator.get_page(page)
    ngrams = trigrams = [create_ngram(a.word, 3) for a in articles[0::num_by_page]]

    for idx in range(1, len(trigrams)-1):
        n = 3
        while True:
            if n > len(articles[0::num_by_page][idx].word):
                break
            prev_ng = create_ngram(articles[0::num_by_page][idx-1].word, n)
            next_ng = create_ngram(articles[0::num_by_page][idx+1].word, n)
            ngrams[idx] = create_ngram(articles[0::num_by_page][idx].word, n)

            if ngrams[idx][0:n] != prev_ng and ngrams[idx][0:n] != next_ng:
                break
            n += 1

    for idx in range(0, len(ngrams)-1):
        if idx+1 <= len(ngrams):
            ngrams[idx] = ngrams[idx] + ' ·· ' + ngrams[idx+1]

    if len(page_obj):
        trigrams_dict = dict(
            zip(
                range(1, len(trigrams) + 1),
                ngrams
            )
        )

    return type('Content', (object,),
                {
                    'page_obj': page_obj,
                    'trigrams_dict': trigrams_dict
                })()
