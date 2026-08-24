from django.test import TestCase

from ..helpers import compact_article_html
from ..models import Article, ArticleAddition


class CompactArticleHtmlTestCase(TestCase):
    def test_drops_newlines_indent_and_tabs(self):
        src = "<b>kohde</b>\n  <i>см.</i>\tlemma"
        self.assertEqual(compact_article_html(src), "<b>kohde</b> <i>см.</i> lemma")

    def test_keeps_single_spaces_between_words(self):
        src = "<b>a</b> foo bar"
        self.assertEqual(compact_article_html(src), src)

    def test_article_save_compacts_html(self):
        art = Article.objects.create(
            word="kohde-fmt",
            article_html="<b>kohde</b>\n  <i>см.</i> lemma",
        )
        art.refresh_from_db()
        self.assertEqual(art.article_html, "<b>kohde</b> <i>см.</i> lemma")

    def test_addition_save_compacts_html(self):
        art = Article.objects.create(word="kohde-add")
        addition = ArticleAddition.objects.create(
            article=art,
            article_html="<b>x</b>\n\ty",
        )
        addition.refresh_from_db()
        self.assertEqual(addition.article_html, "<b>x</b> y")
