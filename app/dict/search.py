from django.contrib.postgres.search import TrigramSimilarity
from django.db.models.functions import Length
from django.core.paginator import Paginator
from django.db.models import F

from .helpers import sorted_by_krl
from .models import *

num_by_page = 18


def search_by_pointer(letter, page):

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


def get_sorted_articles(ids, page):

    articles = sorted(Article.objects.extra(select={'sort_order': "0"}).filter(pk__in=ids).all(),
                      key=lambda el: (
                          sorted_by_krl(el, 'word'),
                      )
                      )

    paginator = Paginator(articles, num_by_page)
    return paginator.get_page(page)


def search_by_translate(query, page=1):

    query = query.replace('ё', 'е')
    ids = ArticleIndexTranslate.objects.filter(rus_word__istartswith=query).values_list('article_id', flat=True)
    return get_sorted_articles(ids, page)


def word_search(query, page):

    query = query \
        .replace('š', 's') \
        .replace('č', 'c') \
        .replace('ž', 'z') \
        .replace('?', '%') \
        .replace('.', '_')

    ids = ArticleIndexWord.objects.filter(word__ilike=query).values_list('article_id', flat=True)
    return get_sorted_articles(ids, page)


def search_possible(query):
    return set(w.word for w in (set(search_trigram(query)) & set(search_levenshtein(query))))


def search_trigram(query):

    return  ArticleIndexWordNormalization.objects.annotate(similarity=TrigramSimilarity('word', query), )\
                          .filter(similarity__gt=0.2)\
                          .order_by('-similarity', Length('word').asc())


def search_levenshtein(query):

    return  ArticleIndexWordNormalization.objects.annotate(
                                lev_dist=Levenshtein(F('word'), query)
                            ).filter(
                                lev_dist__lte=2
                            )\
                            .order_by('-lev_dist', Length('word').asc())

