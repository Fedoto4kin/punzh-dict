import re
from django.shortcuts import render, redirect
from django.utils.http import urlquote
from django.core.paginator import Paginator
from django.views.generic import TemplateView

from .models import *
from .services import sorted_by_krl, normalization, create_ngram

num_by_page = 18


class AboutPageStaticView(TemplateView):

    template_name = 'about.html'


class DialectsStaticView(TemplateView):

    template_name = 'dialects.html'


class IntroStaticView(TemplateView):

    template_name = 'intro.html'


class PunzhStaticView(TemplateView):

    template_name = 'punzh.html'


class TeamStaticView(TemplateView):

    template_name = 'team.html'


def index(request, letter=None, page=1):

    if not letter:
        return render(request, 'index.html')

    articles = Article.objects.all().filter(first_letter=letter.upper())
    last_page_word = ''
    first_page_word = ''
    trigrams_dict = {}

    if len(articles):
        page_obj = sorted(articles,
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

    context = {
        "ABC": KRL_ABC,
        "letter": letter.upper(),
        "last_page_word": last_page_word,
        "first_page_word": first_page_word,
        "trigrams": trigrams_dict,
        'page_obj': page_obj,
    }
    return render(request, 'article_list.html', context)


def search_proc(request):

    query = request.GET.get('query', '')

    if len(query.strip()):

        query = re.sub(r'[^\w\s\.\?]', '', query)
        return redirect('/search/' + urlquote(query.strip()))
    else:
        return render(request, 'search.html',  {"search": "true"})


def article_search(query, page=1):

    articles = Article.objects.filter(article_html__icontains=query)
    articles = sorted(articles,
                      key=lambda el: (
                          sorted_by_krl(el, 'word'),
                      )
                      )
    paginator = Paginator(articles, num_by_page)
    return paginator.get_page(page)


def search_by_translate(query, page=1):

    query = query.replace('ё', 'е')

    pks0 = ArticleIndexTranslate.objects.filter(rus_word__ilike=query).values_list('article_id', flat=True)
    articles = Article.objects.extra(select={'sort_order': "0"}).filter(pk__in=pks0).all()

    articles = sorted(articles,
                      key=lambda el: (
                          sorted_by_krl(el, 'word'),
                      )
                      )

    paginator = Paginator(articles, num_by_page)

    return paginator.get_page(page)


def word_search(query, page):

    query = query \
        .replace('š', 's') \
        .replace('č', 'c') \
        .replace('ž', 'z') \
        .replace('?', '%') \
        .replace('.', '_')

    pks0 = ArticleIndexWord.objects.filter(word__ilike=query + '%').values_list('article_id', flat=True)
    articles = Article.objects.extra(select={'sort_order': "0"}).filter(pk__in=pks0).all()

    articles = sorted(articles,
                      key=lambda el: (
                          sorted_by_krl(el, 'word'),
                      )
                      )

    paginator = Paginator(articles, num_by_page)
    return paginator.get_page(page)


def search(request, query='', page=1):

    if re.match(r'[А-яЁё\s]', query):
        page_obj = search_by_translate(query, page)
    else:
        page_obj = word_search(query, page)

    context = {
        "ABC": KRL_ABC,
        "query": query,
        "search": "true",
        'page_obj': page_obj
    }
    return render(request, 'search.html', context)
