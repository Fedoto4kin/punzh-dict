import os
import sys
import re
import django
from bs4 import BeautifulSoup as bs

sys.path.append('../')

os.environ["DJANGO_SETTINGS_MODULE"] = 'punzh.settings'
django.setup()

from dict.models import Article, ArticleIndexTranslate


def find_rus_translation(text):

    text = re.sub(r'\(.*\)', '', text)
    df = re.search(r'^([\-А-яЁё\s,.;]+)(?:;|$)', text)
    if df:
        return df.group()\
                  .strip()\
                  .replace('ё', 'e')


def split_by_li(html):

    r = []
    parent = html.find("ol")
    if parent:
        for li in parent.find_all("li"):
            for tag in li.findAll():
                tag.replace_with('')
            r.append(li)
        return r

    for tag in html.findAll():
        tag.replace_with('')

    return [html]


def create_translation(article_html):

    return []


def prepare_trans_list(t):

    l = []
    l += re.split(r'[,;]', t)

    return l

def prepare_trans_list_additional(t):

    exclude = {'в', 'без', 'до', 'из', 'к', 'на', 'по', 'о', 'от', 'перед', 'при', 'через', 'с', 'у', 'и', 'или', 'не'
               'нет', 'за', 'над', 'для', 'об', 'под', 'про', 'да', 'и',  'т.', 'д.',
               'кого-л.', 'что-л.', 'каких-л.', 'что-л.', 'чему-л.', 'чем-л.', 'чего-л.', 'какую-л.', 'кем-л',
               'какого-л.', 'куда-л.', 'кому-л.',
               '-'}
    l = []
    l += t.split()
    if len(l) > 1:
        l = set(l) - exclude
        return l
    else:
        return []


if __name__ == '__main__':

    for a in Article.objects.all():

        trans = []
        data = bs(a.article_html, 'html.parser')

        for _ in split_by_li(data):
            t = find_rus_translation(_.text)
            if t is not None:
                for __ in prepare_trans_list(t):
                    trans.append(__.strip())
                    for ___ in prepare_trans_list_additional(__):
                        trans.append(___)
        if len(trans) > 0:
            indx = (ArticleIndexTranslate(article=a, rus_word=var) for var in set(trans) if len(var) != 0)
            ArticleIndexTranslate.objects.bulk_create(indx)
            print(a)
            print(trans)
            print('---------------------------')
