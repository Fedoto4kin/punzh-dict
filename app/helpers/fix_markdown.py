import os
import sys
import re
import django
from bs4 import BeautifulSoup as bs

sys.path.append('../')


# todo: doctests
os.environ["DJANGO_SETTINGS_MODULE"] = 'punzh.settings'
django.setup()

from dict.models import Article

# todo: create class and incasulate article and functions

def replace_cyr_by_lat_b(article_html):
    b = re.search(r'<b>(.*)</b>', article_html)
    return article_html.replace(
        b.group(),
        b.group()
            .replace('р', 'p')
            .replace('е', 'e')
            .replace('о', 'o')
            .replace('а', 'a')
    )

def fix_puncts(article_html):

    for _ in re.finditer(r'\s([,;:\!\?\.]{1})', article_html):
        if _:
            article_html = article_html.replace(
                _.group(),
                _.group(1)
            )

    for _ in re.finditer(r'\s([,;:\!\?\.]{1})', article_html):
        if _:
            article_html = article_html.replace(
                _.group(),
                _.group(1)
            )
    return article_html


def strip_b(article_html):
    article_html = article_html.replace('<b>,</b>', ',')
    article_html = article_html.replace('<b>’</b>', '’')

    content = bs(article_html, "html.parser")
    for _ in content.findAll('b'):
        if _.text:
            _.string = _.text.strip()
    return str(content)


def strip_i(article_html):
    content = bs(article_html, "html.parser")
    for _ in content.findAll('i'):
        if _.text:
            _.string = _.text.strip()
    return str(content)


def split_i(article_html):
    # ure very carefully !
    for i in re.findall(r'<i>(?!\()(.*?)(?!\))</i>', article_html):
        if i and ' ' in i:
            article_html = article_html.replace(
                i,
                '</i> <i>'.join(
                    i.split()
                )
            )
    return article_html


def move_dote_inside_i(article_html):

    i = re.search(r'<i>([A-я]+)</i>\s?\.', article_html)
    if i:
        article_html = article_html.replace(
            i.group(),
            '<i>{}.</i>'.format(i.group(1))
        )

    return article_html


def cyr_to_lat_abbr(article_html):

    article_html = article_html.replace('<i>тот</i>', '<i>mom</i>')
    article_html = article_html.replace('<i>сот</i>', '<i>com</i>')
    article_html = article_html.replace('<i>сотр</i>', '<i>comp</i>')
    article_html = article_html.replace('<i>пит</i>', '<i>num</i>')
    article_html = article_html.replace('<i>рrер</i>', '<i>prep</i>')
    article_html = article_html.replace('<i>desсr</i>', '<i>descr</i>')
    article_html = article_html.replace('<i>сom</i>', '<i>com</i>')

    return article_html


def lat_to_cyr_abbr(article_html):

    article_html = article_html.replace('<i>cp.</i>', '<i>ср.</i>')  # lat -> cyr
    article_html = article_html.replace('<i>cp</i>', '<i>ср.</i>')  # lat -> cyr
    article_html = article_html.replace('<i>cм</i>', '<i>см.</i>')  # lat -> cyr
    article_html = article_html.replace('<i>см</i>', '<i>см.</i>')  # lat -> cyr
    return article_html


def fix_misread_abbr(article_html):

    article_html = article_html.replace('<i>com.</i>', '<i>com</i>')
    article_html = article_html.replace('<i>postp.</i>', '<i>postp</i>')
    return article_html


def fix_artefacts(article_html):

    article_html = article_html.replace(' <i>:</i>', ':')
    article_html = article_html.replace(' <i>.</i>', '.')
    article_html = article_html.replace(':</i>', '</i>:')
    article_html = article_html.replace('<i>а</i>', '<i>a</i>')  # cyr -> lat
    article_html = article_html.replace('<i>в</i> <i>знач.</i>', '<i>в знач.</i>')
    article_html = article_html.replace('</i> . ', '.</i> ')
    article_html = article_html.replace('<i>.</i>', '.')
    article_html = article_html.replace('<i>~</i>', '~')
    article_html = article_html.replace('</i>–<i>', '–')
    article_html = article_html.replace('<i>–</i>', '–')
    article_html = article_html.replace('</i>’<i>', '’')
    article_html = article_html.replace('<i>’</i>', '’')
    article_html = article_html.replace('</i><i>', '</i> <i>')
    article_html = article_html.replace('</i> иs</i>', 'и <i>s</i>')
    article_html = article_html.replace('</i> иa</i>', 'и <i>a<i>')
    article_html = article_html.replace('и<i>s</i>', 'и <i>s</i>')
    article_html = article_html.replace('и<i>a</i>', 'и <i>a</i>')

    return article_html

def fix_whitespace_after_i(article_html):

    for _ in re.finditer(r'</i>([A-zA-я]+)', article_html):
        if _:

            article_html = article_html.replace(
                _.group(),
                '</i> {}'.format(_.group(1))
            )
    return article_html


def hotfix(article_html):

    article_html = article_html.replace('<i>a<i>', '<i>a</i>')
    article_html = article_html.replace('<i>s<i>', '<i>s</i>')

    return article_html


if __name__ == '__main__':

    for a in Article.objects.all():
    #for a in Article.objects.filter(first_letter='H'):

        a.article_html = strip_b(a.article_html)
        a.article_html = strip_i(a.article_html) # Every first
        a.article_html = split_i(a.article_html)

        a.article_html = fix_artefacts(a.article_html)
        a.article_html = fix_misread_abbr(a.article_html)
        a.article_html = cyr_to_lat_abbr(a.article_html)
        a.article_html = lat_to_cyr_abbr(a.article_html)
        a.article_html = move_dote_inside_i(a.article_html)
        a.article_html = fix_puncts(a.article_html)
        a.article_html = fix_whitespace_after_i(a.article_html)
        print(a.article_html)
        # a.save()
