import os
import re
import django
from bs4 import BeautifulSoup as bs

os.environ["DJANGO_SETTINGS_MODULE"] = 'punzh.settings'
django.setup()

from dict.models import Article

def filter(art):

    # remove wrong tags
    invalid_tags = ['font', 'a', 'p', 'img', 'br']
    for tag in art.findAll():
        if tag.name in invalid_tags:
            tag.replaceWithChildren()

    for tag in art.find_all('span', attrs={"lang": "et-EE"}):
        tag.replaceWithChildren()

    for tag in art.find_all('span', attrs={"lang": "fi-FI"}):
        tag.replaceWithChildren()

    for tag in art.find_all('span', attrs={"lang": "en-US"}):
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
        .replace('</b> <b>', ' ') \
        .replace('</i>', '</i> ') \
        .replace(' </i>', '</i>') \
        .replace(' </b><i>', '</b> <i>') \
        .replace('</b><i>', '</b> <i>') \
        .replace(' ;', ';')

    art = ' '.join(art.split())
    return bs(art, "html.parser")


def create_list(text):
    s = re.split("[1-9]+\.\s{1}", text)
    if len(s) > 1:
        text = s[0]
        text += '<ol>'
        text += ''.join(['<li>' + _ + "</li>" for _ in s[1:]])
        text += '</ol>'
    return text


def replace_tilde(content, word):

    base = re.split(r'\|+', word.split()[0])[0]
    return content.replace('~', base) \
                  .replace('||', '') \
                  .replace('|', '<span class="text-muted font-weight-normal">|</span>')


def create_article(content):

    # remove wrap
    for _ in content.findAll('p'):
        _.replaceWithChildren()

    if len(content.get_text().strip()):
        word = content.find('b') \
                      .get_text() \
                      .strip()

        html = str(content).rstrip().strip()

        article_html = create_list(html)

        article = Article(
            word=word,
            article_html=article_html
        )
        print(article_html)
        article.save()
        print(article, ' [OK]')


def get_content(content):

    for art in content.find_all('p'):
        create_article(filter(art))


if __name__ == '__main__':

    # TODO: variable
    with open("data/Nv3.html") as file:
        data = file.read()

    content = bs(data,  "html.parser")
    get_content(content.find("div", {"id": "TextSection"}))



