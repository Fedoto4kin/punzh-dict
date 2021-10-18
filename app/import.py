import os
import re
import django
from bs4 import BeautifulSoup as bs

os.environ["DJANGO_SETTINGS_MODULE"] = 'punzh.settings'
django.setup()

from dict.models import Article


def filter(art):

    # remove wrong tags
    invalid_tags = ['font', 'a', 'p', 'img', 'br', 'span']

    for tag in art.findAll():
        if tag.name in invalid_tags:
            tag.replaceWithChildren()

    # remove empty tags
    for x in art.find_all():
        if len(x.get_text(strip=True)) == 0:
            x.extract()

    # remove other trash
    art = str(art) \
        .replace('\t', ' ') \
        .replace('\n', ' ') \
        .replace('</b><b>', '') \
        .replace('</b>|<b>', '|') \
        .replace('</b>||<b>', '||') \
        .replace('</b>,<b>', ',') \
        .replace('</b> <b>', ' ') \
        .replace('</b><i>', '</b> <i>') \
        .replace(' ;', ';') \
        .replace('ʼ', '’') \
        .replace('</b>’<b>', '’') \
        .replace('<b>’</b>', '’')

    art = ' '.join(art.split())
    return bs(art, "html.parser")


def create_list(text):
    s = re.split("[1-9]{1}\.\s", text)
    if len(s) > 1:
        text = s[0]
        text += '<ol>'
        text += ''.join(['<li>' + _ + "</li>" for _ in s[1:]])
        text += '</ol>'
    return text



def create_article(content):

    # remove wrap
    for _ in content.findAll('p'):
        _.replaceWithChildren()

    if len(content.get_text().strip()):
        word = content.find('b') \
                      .get_text() \
                      .strip()

        word = word.replace(chr(1072), chr(97)) \
                   .replace(chr(1077), chr(101)) \
                   .replace(chr(1086), chr(111)) \
                   .replace(chr(1089), chr(99)) \
                   .replace(chr(1088), chr(112))

        html = str(content).rstrip().strip()

        article_html = create_list(html)

        article = Article(
            word=word,
            article_html=article_html
        )
        article.save()
        print(article, ' [OK]')


def get_content(content):

    for art in content.find_all('p'):
        create_article(filter(art))


if __name__ == '__main__':

    # TODO: variable
    with open("data/Kv3.html") as file:
        data = file.read()

    contents = bs(data,  "html.parser")
    for content in contents.findAll("div"):
        get_content(content)
