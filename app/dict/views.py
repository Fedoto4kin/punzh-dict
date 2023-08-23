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
        return render(request, 'search.html', {"search": "true"})


def search(request, query='', page=1):

    query = query.strip()
    if re.match(r'[.А-Яа-яЁё\s]', query):
        page_obj = search_by_translate_linked(query, page)
    else:
        query = query.replace(';', '').replace('’', '').replace(',', '')
        page_obj = word_search(query, page)

    possible = []
    if not len(page_obj.object_list):
        possible = search_possible(query)

    context = {
        "ABC": KRL_ABC,
        "query": query,
        "search": "true",
        "page_obj": page_obj,
        "possible": possible
    }
    return render(request, 'search.html', context)


def tag_search(request, tags='', page=1):
    content = type('Content', (object,), {
        'page_obj': None,
        'trigrams_dict': None
    })()

    tmp_list = set(tags.split(','))
    try:
        tag_ids = [int(x.strip()) for x in tmp_list]
    except:
        tag_ids = []

    all_tags = get_tags_by_type()
    geo_tags = get_tags_by_type(1)
    linguistic_tags = get_tags_by_type(2)
    tag_tags = get_tags_by_type(3)
    dialect_tags = get_tags_by_type(4)
    other_tags = get_tags_by_type(5)

    tags_selected = get_tags_by_ids_distinct(tag_ids)

    if len(tag_ids):
        content = search_by_tags_smart(
            by_geo=list(set(geo_tags.values_list('pk', flat=True)) & set(tag_ids)),
            by_tags=list(set(tag_tags.values_list('pk', flat=True)) & set(tag_ids)),
            by_dialect=list(set(dialect_tags.values_list('pk', flat=True)) & set(tag_ids)),
            by_ling=list(set(linguistic_tags.values_list('pk', flat=True)) & set(tag_ids)),
            by_other=list(set(other_tags.values_list('pk', flat=True)) & set(tag_ids)),
            page=page
        )

    context = {
        "ABC": KRL_ABC,
        "tagIds": tag_ids,
        "tags_selected": tags_selected,
        "allTags": {
            'all': all_tags,
            'geo': geo_tags,
            'linguistic': linguistic_tags,
            'tag': tag_tags,
            'dialect': dialect_tags,
            'other': other_tags

        },
        'query': ",".join(map(str, tag_ids)),
        "page_obj": content.page_obj,
        "trigrams": content.trigrams_dict,
    }
    return render(request, 'tags.html', context)
