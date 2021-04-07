from django.shortcuts import render, redirect
from .models import Article, SearchWord, KRL_ABC
from django.core.paginator import Paginator
from itertools import chain


num_by_page = 18


def index(request, letter='A', page=1):

    articles = Article.objects.all().filter(first_letter=letter.upper())
    last_page_trigram = ''
    first_page_trigram = ''
    trigrams_dict = {}

    if len(articles):
        articles = sorted(articles,
                          key=lambda article: [
                              Article.get_krl_abc().index(c)
                              for c in ''.join(
                                      [c for c in article.first_trigram if c in set(Article.get_krl_abc())]
                                  )
                              ]
                          )

    paginator = Paginator(articles, num_by_page)
    page_obj = paginator.get_page(page)

    trigrams = [a.first_trigram for a in articles[0::num_by_page]]

    if len(page_obj):
        last_page_trigram = page_obj[-1].first_trigram
        first_page_trigram = page_obj[0].first_trigram
        trigrams_dict = dict(zip(range(1, len(trigrams) + 1), trigrams))

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
        return redirect('search/' + query)
    else:
        return render(request, 'search.html',  {"search": "true"})



def search(request, query='', page=1):

    query = query
    ex_pk = []

    pks0 = SearchWord.objects.filter(word__iexact=query).values_list('article_id', flat=True)
    articles0 = Article.objects.filter(pk__in=pks0).all()
    ex_pk += pks0

    pks1 = SearchWord.objects.filter(word__istartswith=query).values_list('article_id', flat=True)
    articles1 = Article.objects.filter(pk__in=pks1).exclude(pk__in=ex_pk).all()
    ex_pk += pks1

    # pks2 = SearchWord.objects.filter(word__icontains=query).values_list('article_id', flat=True)
    # articles2 = Article.objects.filter(pk__in=pks2).exclude(pk__in=ex_pk).all()
    # ex_pk += pks1

    # pks3 = SearchText.objects.filter(text__icontains=search.strip())  # todo: smart search
    # articles3 = Article.objects.filter(pk__in=pks3).exclude(pk__in=ex_pk).all()

    articles = list(chain( articles0, articles1))

    paginator = Paginator(articles, num_by_page)
    page_obj = paginator.get_page(page)

    context = {
        "ABC": KRL_ABC,
        "query": query,
        "search": "true",
        'page_obj': page_obj
    }

    return render(request, 'search.html', context)
