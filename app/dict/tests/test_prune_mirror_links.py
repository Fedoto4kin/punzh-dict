from django.core.management import call_command
from django.test import TestCase
from io import StringIO

from dict.models import Article, ArticleLink


class PruneMirrorLinksTestCase(TestCase):
    def test_drops_reverse_when_only_one_html_has_see(self):
        donor = Article.objects.create(
            word="ruttoh", article_html="<b>ruttoh</b> быстро"
        )
        stub = Article.objects.create(
            word="rutoldi", article_html="<b>rutoldi</b> <i>см.</i> ruttoh"
        )
        ArticleLink.objects.create(from_article=stub, to_article=donor)
        mirror = ArticleLink.objects.create(from_article=donor, to_article=stub)

        call_command("prune_mirror_links", apply=True, stdout=StringIO())

        self.assertTrue(
            ArticleLink.objects.filter(from_article=stub, to_article=donor).exists()
        )
        self.assertFalse(ArticleLink.objects.filter(pk=mirror.pk).exists())

    def test_keeps_mutual_see(self):
        a = Article.objects.create(
            word="abie", article_html="<b>abie</b> <i>ср.</i> abevus"
        )
        b = Article.objects.create(
            word="abevus", article_html="<b>abevus</b> <i>ср.</i> abie"
        )
        ArticleLink.objects.create(from_article=a, to_article=b)
        ArticleLink.objects.create(from_article=b, to_article=a)

        call_command("prune_mirror_links", apply=True, stdout=StringIO())

        self.assertEqual(2, ArticleLink.objects.count())

    def test_dry_run_does_not_delete(self):
        donor = Article.objects.create(
            word="ruttoh", article_html="<b>ruttoh</b> быстро"
        )
        stub = Article.objects.create(
            word="rutoldi", article_html="<b>rutoldi</b> <i>см.</i> ruttoh"
        )
        ArticleLink.objects.create(from_article=stub, to_article=donor)
        ArticleLink.objects.create(from_article=donor, to_article=stub)

        call_command("prune_mirror_links", stdout=StringIO())

        self.assertEqual(2, ArticleLink.objects.count())
