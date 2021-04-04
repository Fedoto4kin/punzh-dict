from django.shortcuts import render, redirect
from .models import Article, KRL_ABC
from django.core.paginator import Paginator


def index(request, letter='A', page=1):

    articles = Article.objects.all().filter(first_letter=letter.upper())

    if len(articles):

        articles = sorted(articles,
                          key=lambda article: [
                              Article.get_krl_abc().index(c)
                              for c in ''.join(
                                      [c for c in article.word if c in set(Article.get_krl_abc())]
                                  )
                              ]
                          )

    paginator = Paginator(articles, 20)
    page_obj = paginator.get_page(page)

    trigrams = [a.first_trigram for a in articles[0::20]]
    trigrams_dict = dict(zip(range(1, len(trigrams)+1), trigrams))

    context = {
        "ABC": KRL_ABC,
        "letter": letter.upper(),
        "trigrams": trigrams_dict,
        'page_obj': page_obj,
    }

    return render(request, 'article_list.html', context)
