from django.core.management import call_command
from django.test import TestCase
from io import StringIO

from dict.models import Article, ArticleLink


class CheckArticleLinksTestCase(TestCase):
    def test_reports_missing_and_extra(self):
        donor = Article.objects.create(
            word="ruttoh", article_html="<b>ruttoh</b> быстро"
        )
        stub = Article.objects.create(
            word="rutoldi",
            article_html="<b>rutoldi</b> <i>см.</i> ruttoh",
        )
        other = Article.objects.create(word="abie", article_html="<b>abie</b> плохой")
        ArticleLink.objects.create(from_article=stub, to_article=other)

        out = StringIO()
        call_command("check_article_links", stdout=out)
        text = out.getvalue()
        self.assertIn("A  в HTML есть лемма", text)
        self.assertIn("rutoldi", text)
        self.assertIn("B  ArticleLink есть", text)

    def test_reports_incomplete_comma_list(self):
        a = Article.objects.create(word="akka", article_html="<b>akka</b> женщина")
        b = Article.objects.create(word="naine", article_html="<b>naine</b> женщина")
        src = Article.objects.create(
            word="muččo",
            article_html="<b>muččo</b> <i>ср.</i> akka, naine",
        )
        ArticleLink.objects.create(from_article=src, to_article=a)

        out = StringIO()
        call_command("check_article_links", stdout=out)
        text = out.getvalue()
        self.assertIn("список см./ср. из нескольких лемм", text)
        self.assertIn("muččo", text)
        self.assertIn("naine", text)

    def test_pipe_headword_existing_link_not_a_or_b(self):
        target = Article.objects.create(
            word="ehät’||t’iä",
            article_html="<b>ehät’||t’iä</b> тащить",
        )
        src = Article.objects.create(
            word="ähät’t’iä",
            article_html="<b>ähät’t’iä</b> <i>см.</i> ehät’t’iä",
        )
        ArticleLink.objects.create(from_article=src, to_article=target)

        out = StringIO()
        call_command("check_article_links", stdout=out)
        text = out.getvalue()
        self.assertRegex(text, r"A  в HTML есть лемма.*: 0")
        self.assertRegex(text, r"B  ArticleLink есть.*: 0")

    def test_illustration_after_semicolon_not_a_gap(self):
        target = Article.objects.create(
            word="ad’ivo",
            article_html="<b>ad’ivo</b> гостья",
        )
        src = Article.objects.create(
            word="ad’vo",
            article_html="<b>ad’vo</b> <i>см.</i> ad’ivo; istuw kun ~",
        )
        ArticleLink.objects.create(from_article=src, to_article=target)

        out = StringIO()
        call_command("check_article_links", stdout=out)
        text = out.getvalue()
        self.assertNotIn("istuw", text)
        self.assertRegex(text, r"список см./ср. из нескольких лемм.*: 0")
