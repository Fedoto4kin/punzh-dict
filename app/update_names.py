import os
import re
import django
from bs4 import BeautifulSoup as bs

# todo: doctests

os.environ["DJANGO_SETTINGS_MODULE"] = 'punzh.settings'
django.setup()

from dict.models import Article


# todo: create methods
# todo: replace тот, сот, пит by com, num, comp
# todo: replace cyr а in <i></i> by lat


def replace_cyr_by_lat(article_html):
    b = re.search(r'<b>(.*)</b>', article_html)
    return article_html.replace(
        b.group(),
        b.group()
            .replace('р', 'p')
            .replace('е', 'e')
            .replace('о', 'o')
            .replace('а', 'a')
    )


def strip_i(article_html):
    content = bs(article_html, "html.parser")
    for _ in content.findAll('i'):
        print(_)
        if _.text:
            _.string = _.text.strip()
    return str(content)


def split_i(article_html):
    for i in re.findall(r'<i>(?!\()(.*?)</i>', article_html):
        if i and ' ' in i:
            article_html = article_html.replace(
                i,
                '</i> <i>'.join(
                    i.split()
                )
            )
    return article_html


def i_whitespaces(article_html):
    # todo: add whitespaces before <i> and after </i> if its no and if after no .,;:
    # todo: move not . outside of <i>
    # todo: remove whitespace if after </i> ,.:;
    return article_html


def cyr_to_lat_abbr(article_html):

    article_html = re.sub(r'(<i>сот</i>)', '<i>com</i>', article_html)
    article_html = re.sub(r'(<i>пит</i>)', '<i>num</i>', article_html)
    article_html = re.sub(r'(<i>тот</i>)', '<i>mom</i>', article_html)
    article_html = re.sub(r'(<i>сотр</i>)', '<i>comp</i>', article_html)

    return article_html



if __name__ == '__main__':

    for a in Article.objects.all():
        # a.article_html = replace_cyr_by_lat(a.article_html)
        # a.article_html = strip_i(a.article_html)
        # a.article_html = split_i(a.article_html)
        # a.article_html = cyr_to_lat_abbr(a.article_html)
        a.article_html = i_whitespaces(a.article_html)

        # a.article_html = re.sub(r'(<i>\s?сот\s?</i>)', '<i>com</i>', a.article_html)
        # a.article_html = re.sub(r'(<i>\s?пит\s?</i>)', '<i>num</i>', a.article_html)

        # a.article_html = re.sub(r'(<i>\s?вcг.\s?</i>)', '<i>всг.</i>', a.article_html)
        # a.article_html = re.sub(r'(<i>\s?тот\s?</i>)', '<i>mom</i>', a.article_html)
        # a.article_html = re.sub(r'(<i>\s?сотр\s?</i>)', '<i>comp</i>', a.article_html)

        # print(a.article_html)
        # a.save()
