import os
import sys
import re
import django
from bs4 import BeautifulSoup as bs

sys.path.append('../')

os.environ["DJANGO_SETTINGS_MODULE"] = 'punzh.settings'
django.setup()

from dict.models import Article, ArticleIndexWord


def find_linked(pattern, num=None):

    pattern = pattern \
        .replace('š', 's') \
        .replace('č', 'c') \
        .replace('ž', 'z') \
        .replace(';', '') \
        .replace('’', '')

    if num:
        ars = ArticleIndexWord.objects.filter(word__ilike=pattern).all()
        for ar in ars:
            if ar.article.word.endswith(' ' + num):
                return ar.article

    ar = ArticleIndexWord.objects.filter(word__ilike=pattern).first()
    return ar.article


def save_linked(article, linked_article):
    article.linked_article=linked_article
    article.save()
    #linked_article.linked_article=article
    #linked_article.save()

if __name__ == '__main__':

    for a in Article.objects.all():

        try:
            found = re.search('<i>см\.<\/i>\s([\S]+)\s([I]){0,3}', a.article_html)
            pattern = found.group(1)
            if pattern:
                print('-----------------')
                print(a.article_html)
                print('    ***      ')
                ln_a = find_linked(pattern, found.group(2))
                if ln_a:
                    save_linked(a, ln_a)
                    print(a.linked_article)
                    print(ln_a.linked_article)

        except AttributeError:
            found = ''  # apply your error handling




