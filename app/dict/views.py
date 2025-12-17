from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils.http import urlquote
from django.views.generic import TemplateView

from .helpers import *
from .search import *


class StaticView(TemplateView):

    template_name = None

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)


def index(request, letter=None, page=1):

    def _get404():
        _context = {
            "ABC": KRL_ABC,
            "letter": letter.upper(),
        }
        return render(request, '404.html', _context, status=404)

    if not letter:
        return render(request, 'index.html')

    if letter.upper() not in KRL_ABC:
        return _get404()

    content = search_by_pointer(letter, page)
    if page > content.page_obj.paginator.num_pages or page < 1:
        print(page)
        print(content.page_obj.paginator.num_pages)
        return _get404()

    current_trigram = ''
    if len(content.trigrams_dict) > 1:
        current_trigram = f' ({content.trigrams_dict.get(page)})'
    context = {
        "ABC": KRL_ABC,
        "letter": letter.upper(),
        "last_page_word": content.last_page_word,
        "first_page_word": content.first_page_word,
        "trigrams": content.trigrams_dict,
        'page_obj': content.page_obj,
        "current_trigram": current_trigram,
    }
    return render(request, 'article_list.html', context)

num_by_page = 18

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
        direction = 'rus'
        translation_table = str.maketrans({
            'ё': 'е',
            '?': '%',
            '.': '_'
        })
        page_obj, found_count, possible = search_by_translate_linked(query.translate(translation_table), page)
    else:
        direction = 'krl'
        translation_table = str.maketrans({
            ';': '',
            '’': '',
            ',': '',
            'š': 's',
            'č': 'c',
            'ž': 'z',
            '?': '%',
            '.': '_'
        })
        page_obj, found_count = word_search(query.translate(translation_table), page)
        possible = []
        if not len(page_obj.object_list):
            possible = search_possible(query)
    context = {
        "ABC": KRL_ABC,
        "query": query,
        "search": "true",
        "page_obj": page_obj,
        "possible": possible,
        "found_count": found_count,
        "direction": direction
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
