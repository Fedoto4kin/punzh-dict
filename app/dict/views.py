from django.shortcuts import render, redirect
from .models import Article, KRL_ABC

def index(request, letter=''):

    articles = []

    if len(letter):
        articles = Article.objects.all().filter(first_letter=letter.upper())

    context = {
        "ABC": KRL_ABC,
        "articles": articles,
        "letter": letter.upper()
    }

    return render(request, 'article_list.html', context)
