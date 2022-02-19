from django.shortcuts import render, redirect
from django.utils.http import urlquote
from django.views.generic import TemplateView


from .helpers import *
from .search import *

num_by_page = 18

class AboutPageStaticView(TemplateView):
    template_name = 'staticPages/about.html'


class DialectsStaticView(TemplateView):
    template_name = 'staticPages/dialects.html'


class IntroStaticView(TemplateView):
    template_name = 'staticPages/intro.html'


class PunzhStaticView(TemplateView):
    template_name = 'staticPages/punzh.html'


class TeamStaticView(TemplateView):
    template_name = 'staticPages/team.html'


def index(request, letter=None, page=1):

    if not letter:
        return render(request, 'index.html')

    content = search_by_pointer(letter, page)

    context = {
        "ABC": KRL_ABC,
        "letter": letter.upper(),
        "last_page_word": content.last_page_word,
        "first_page_word": content.first_page_word,
        "trigrams": content.trigrams_dict,
        'page_obj': content.page_obj,
    }
    return render(request, 'article_list.html', context)

def search_proc(request):

    query = request.GET.get('query', '')
    if len(query.strip()):
        query = re.sub(r'[^\w\-\s\.\?]', '', query)
        return redirect('/search/' + urlquote(query.strip()))
    else:
        return render(request, 'search.html',  {"search": "true"})


def search(request, query='', page=1):

    if re.match(r'[А-яЁё\s]', query):
        page_obj = search_by_translate(query, page)
    else:
        page_obj = word_search(query, page)

    context = {
        "ABC": KRL_ABC,
        "query": query,
        "search": "true",
        "page_obj": page_obj
    }
    return render(request, 'search.html', context)
