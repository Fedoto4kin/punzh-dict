import re
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from itertools import chain

from .models import *
from .services import sorted_by_krl


num_by_page = 18


def index(request, letter='A', page=1):

    articles = Article.objects.all().filter(first_letter=letter.upper())
    last_page_trigram = ''
    first_page_trigram = ''
    trigrams_dict = {}

    if len(articles):
        articles = sorted(articles,
                          key=lambda el: (
                              sorted_by_krl(el),
                              sorted_by_krl(el, 'word')
                          )
                          )

    paginator = Paginator(articles, num_by_page)
    page_obj = paginator.get_page(page)
    trigrams = [a.first_trigram for a in articles[0::num_by_page]]

    if len(page_obj):
        last_page_trigram = page_obj[-1].first_trigram
        first_page_trigram = page_obj[0].first_trigram
        trigrams_dict = dict(
            zip(
                range(1, len(trigrams) + 1),
                trigrams
            )
        )

    context = {
        "ABC": KRL_ABC,
        "letter": letter.upper(),
        "last_page_trigram": last_page_trigram,
        "first_page_trigram": first_page_trigram,
        "trigrams": trigrams_dict,
        'page_obj': page_obj,
    }
    return render(request, 'article_list.html', context)


def search_proc(request):

    query = request.GET.get('query', '')
    if len(query.strip()):
        query = re.sub('[^А-яЁё' + Article.get_krl_abc() + 'i̮\s\-]', '', query)
        return redirect('/search/' + query)
    else:
        return render(request, 'search.html',  {"search": "true"})


def search(request, query='', page=1):

    query = query
    ex_pk = []

    pks0 = ArticleIndexWord.objects.filter(word__iexact=query).values_list('article_id', flat=True)
    articles0 = Article.objects.filter(pk__in=pks0).all()
    ex_pk += pks0

    pks1 = ArticleIndexWord.objects.filter(word__istartswith=query).values_list('article_id', flat=True)
    articles1 = Article.objects.filter(pk__in=pks1).exclude(pk__in=ex_pk).all()

    articles = list(chain(articles0, articles1))

    # TODO: sorting
    paginator = Paginator(articles, num_by_page)
    page_obj = paginator.get_page(page)



    context = {
        "ABC": KRL_ABC,
        "query": query,
        "search": "true",
        'page_obj': page_obj
    }
    return render(request, 'search.html', context)
