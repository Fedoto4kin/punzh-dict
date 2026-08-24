from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from dict.models import Article, ArticleLink
from dict.see_audit import lookup_articles, scan_see_links


class ScanSeeLinksTestCase(TestCase):
    def test_unique_missing_and_extra(self):
        donor = Article.objects.create(
            word="ruttoh", article_html="<b>ruttoh</b> быстро"
        )
        other = Article.objects.create(word="abie", article_html="<b>abie</b> плохой")
        stub = Article.objects.create(
            word="rutoldi",
            article_html="<b>rutoldi</b> <i>см.</i> ruttoh",
        )
        extra = ArticleLink.objects.create(from_article=stub, to_article=other)
        scan = scan_see_links(stub, [extra])
        self.assertEqual(len(scan["unique_missing"]), 1)
        self.assertEqual(scan["unique_missing"][0]["target"].id, donor.id)
        self.assertEqual(scan["extra"], [extra])
        self.assertFalse(scan["unresolved"])
        self.assertFalse(scan["homonym"])

    def test_comma_list_unique_gap(self):
        a = Article.objects.create(word="akka", article_html="<b>akka</b>")
        b = Article.objects.create(word="naine", article_html="<b>naine</b>")
        src = Article.objects.create(
            word="muččo",
            article_html="<b>muččo</b> <i>ср.</i> akka, naine",
        )
        lnk = ArticleLink.objects.create(from_article=src, to_article=a)
        scan = scan_see_links(src, [lnk])
        self.assertEqual([r["target"].id for r in scan["unique_missing"]], [b.id])

    def test_unresolved_lemma(self):
        src = Article.objects.create(
            word="zzzsrc",
            article_html="<b>zzzsrc</b> <i>см.</i> nosuchlemmaxyz",
        )
        scan = scan_see_links(src, [])
        self.assertEqual(scan["unresolved"][0]["lemma"], "nosuchlemmaxyz")

    def test_see_lemma_prefers_simple_headword_over_compound(self):
        target = Article.objects.create(
            word="riw||gu, ~gun’e",
            article_html="<b>riw||gu</b> жердь",
        )
        Article.objects.create(
            word="riwgu|meččä",
            article_html="<b>riwgu|meččä</b>",
        )
        Article.objects.create(
            word="humala|riwgu",
            article_html="<b>humala|riwgu</b>",
        )
        src = Article.objects.create(
            word="aija||š",
            article_html="<b>aija||š</b> <i>см.</i> riwgu",
        )
        found = lookup_articles("riwgu", src.id)
        self.assertEqual([a.word for a in found], ["riw||gu, ~gun’e"])
        scan = scan_see_links(src, [])
        self.assertEqual(len(scan["unique_missing"]), 1)
        self.assertEqual(scan["unique_missing"][0]["target"].id, target.id)
        self.assertFalse(scan["homonym"])
        self.assertFalse(scan["unresolved"])


class FixSeeRefsTestCase(TestCase):
    def test_apply_unique_creates_link_without_html_change(self):
        donor = Article.objects.create(
            word="ruttoh", article_html="<b>ruttoh</b> быстро"
        )
        html = "<b>rutoldi</b> <i>см.</i> ruttoh"
        stub = Article.objects.create(word="rutoldi", article_html=html)
        out = StringIO()
        call_command(
            "fix_see_refs",
            "--apply-unique",
            stdout=out,
        )
        self.assertTrue(
            ArticleLink.objects.filter(from_article=stub, to_article=donor).exists()
        )
        stub.refresh_from_db()
        self.assertEqual(stub.article_html, html)
        self.assertIn("HTML не меняли", out.getvalue())

    def test_apply_unique_is_default_queue_without_crooked(self):
        """Кривой маркер не должен блокировать очередь A при --apply-unique."""
        donor = Article.objects.create(word="baba", article_html="<b>baba</b>")
        src = Article.objects.create(
            word="babus",
            article_html="<b>babus</b> <i>см.</i> baba",
        )
        call_command("fix_see_refs", "--apply-unique", stdout=StringIO())
        self.assertTrue(
            ArticleLink.objects.filter(from_article=src, to_article=donor).exists()
        )

    def test_extra_y_deletes_link(self):
        donor = Article.objects.create(word="ruttoh", article_html="<b>ruttoh</b>")
        other = Article.objects.create(word="abie", article_html="<b>abie</b>")
        stub = Article.objects.create(
            word="rutoldi",
            article_html="<b>rutoldi</b> <i>см.</i> ruttoh",
        )
        ArticleLink.objects.create(from_article=stub, to_article=donor)
        extra = ArticleLink.objects.create(from_article=stub, to_article=other)
        with patch(
            "dict.management.commands.fix_see_refs.Command._ask",
            return_value="y",
        ):
            call_command("fix_see_refs", "--queue", "extra", stdout=StringIO())
        self.assertFalse(ArticleLink.objects.filter(pk=extra.pk).exists())
        self.assertTrue(
            ArticleLink.objects.filter(from_article=stub, to_article=donor).exists()
        )

    def test_extra_empty_keeps_link(self):
        other = Article.objects.create(word="abie", article_html="<b>abie</b>")
        stub = Article.objects.create(
            word="rutoldi",
            article_html="<b>rutoldi</b> <i>см.</i> ruttoh",
        )
        extra = ArticleLink.objects.create(from_article=stub, to_article=other)
        with patch(
            "dict.management.commands.fix_see_refs.Command._ask",
            return_value="",
        ):
            call_command("fix_see_refs", "--queue", "extra", stdout=StringIO())
        self.assertTrue(ArticleLink.objects.filter(pk=extra.pk).exists())

    def test_homonym_t_creates_chosen_link(self):
        a1 = Article.objects.create(word="kappaI", article_html="<b>kappaI</b>")
        a2 = Article.objects.create(word="kappaII", article_html="<b>kappaII</b>")
        from dict.models import ArticleIndexWord

        ArticleIndexWord.objects.get_or_create(article=a1, word="kappa")
        ArticleIndexWord.objects.get_or_create(article=a2, word="kappa")
        src = Article.objects.create(
            word="srcsee",
            article_html="<b>srcsee</b> <i>см.</i> kappa",
        )
        with patch(
            "dict.management.commands.fix_see_refs.Command._ask",
            return_value=f"t {a2.id}",
        ):
            call_command("fix_see_refs", "--queue", "homonym", stdout=StringIO())
        self.assertTrue(
            ArticleLink.objects.filter(from_article=src, to_article=a2).exists()
        )
        self.assertFalse(
            ArticleLink.objects.filter(from_article=src, to_article=a1).exists()
        )
