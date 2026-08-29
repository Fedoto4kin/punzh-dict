from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from dict.models import Article, ArticleLink, ArticleIndexWord
from dict.see_audit import html_deriv_lemmas, scan_deriv_links


class ScanDerivLinksTestCase(TestCase):
    def test_tagged_freq_unique_missing(self):
        base = Article.objects.create(
            word="ruttoh", article_html="<b>ruttoh</b> быстро"
        )
        derived = Article.objects.create(
            word="rutoldi",
            article_html="<b>rutoldi</b> <i>freq</i> от ruttoh",
        )
        scan = scan_deriv_links(derived, [])
        self.assertEqual(len(scan["unique_missing"]), 1)
        self.assertEqual(scan["unique_missing"][0]["target"].id, base.id)
        self.assertEqual(scan["unique_missing"][0]["source"], "tagged")

    def test_loose_ot_unique_missing(self):
        base = Article.objects.create(word="abie", article_html="<b>abie</b>")
        derived = Article.objects.create(
            word="abien",
            article_html="<b>abien</b> от abie",
        )
        scan = scan_deriv_links(derived, [])
        self.assertEqual(len(scan["unique_missing"]), 1)
        self.assertEqual(scan["unique_missing"][0]["source"], "loose")

    def test_russian_ot_in_illustration_not_picked(self):
        base = Article.objects.create(word="kala", article_html="<b>kala</b>")
        derived = Article.objects.create(
            word="kalas",
            article_html="<b>kalas</b> взял рыбу от берега",
        )
        self.assertEqual(html_deriv_lemmas(derived.article_html), [])
        scan = scan_deriv_links(derived, [])
        self.assertFalse(scan["unique_missing"])

    def test_wrong_kind_see_not_overwritten(self):
        base = Article.objects.create(word="ruttoh", article_html="<b>ruttoh</b>")
        derived = Article.objects.create(
            word="rutoldi",
            article_html="<b>rutoldi</b> <i>freq</i> от ruttoh",
        )
        see_link = ArticleLink.objects.create(
            from_article=derived,
            to_article=base,
            kind=ArticleLink.KIND_SEE,
        )
        scan = scan_deriv_links(derived, [see_link])
        self.assertFalse(scan["unique_missing"])
        self.assertEqual(len(scan["wrong_kind"]), 1)
        self.assertEqual(scan["wrong_kind"][0]["link"].id, see_link.id)

    def test_already_deriv_satisfied(self):
        base = Article.objects.create(word="ruttoh", article_html="<b>ruttoh</b>")
        derived = Article.objects.create(
            word="rutoldi",
            article_html="<b>rutoldi</b> <i>freq</i> от ruttoh",
        )
        deriv_link = ArticleLink.objects.create(
            from_article=derived,
            to_article=base,
            kind=ArticleLink.KIND_DERIV,
        )
        scan = scan_deriv_links(derived, [deriv_link])
        self.assertFalse(scan["unique_missing"])
        self.assertEqual(len(scan["already"]), 1)


class CheckDerivLinksTestCase(TestCase):
    def test_stdout_reports_missing_and_homonym(self):
        base = Article.objects.create(word="ruttoh", article_html="<b>ruttoh</b>")
        a1 = Article.objects.create(word="kappaI", article_html="<b>kappaI</b>")
        a2 = Article.objects.create(word="kappaII", article_html="<b>kappaII</b>")
        ArticleIndexWord.objects.get_or_create(article=a1, word="kappa")
        ArticleIndexWord.objects.get_or_create(article=a2, word="kappa")
        Article.objects.create(
            word="rutoldi",
            article_html="<b>rutoldi</b> <i>freq</i> от ruttoh",
        )
        Article.objects.create(
            word="kappas",
            article_html="<b>kappas</b> <i>freq</i> от kappa",
        )
        out = StringIO()
        call_command("check_deriv_links", stdout=out)
        text = out.getvalue()
        self.assertIn("rutoldi", text)
        self.assertIn("ruttoh", text)
        self.assertIn("омоним", text)
        self.assertIn("kappa", text)


class FixDerivRefsTestCase(TestCase):
    def test_apply_unique_creates_deriv_without_html_change(self):
        base = Article.objects.create(word="ruttoh", article_html="<b>ruttoh</b>")
        html = "<b>rutoldi</b> <i>freq</i> от ruttoh"
        derived = Article.objects.create(word="rutoldi", article_html=html)
        out = StringIO()
        call_command("fix_deriv_refs", "--apply-unique", stdout=out)
        lnk = ArticleLink.objects.get(from_article=derived, to_article=base)
        self.assertEqual(lnk.kind, ArticleLink.KIND_DERIV)
        derived.refresh_from_db()
        self.assertEqual(derived.article_html, html)
        self.assertIn("HTML не меняли", out.getvalue())

    def test_apply_unique_skips_wrong_kind(self):
        base = Article.objects.create(word="ruttoh", article_html="<b>ruttoh</b>")
        derived = Article.objects.create(
            word="rutoldi",
            article_html="<b>rutoldi</b> <i>freq</i> от ruttoh",
        )
        ArticleLink.objects.create(
            from_article=derived,
            to_article=base,
            kind=ArticleLink.KIND_SEE,
        )
        out = StringIO()
        call_command("fix_deriv_refs", "--apply-unique", stdout=out)
        self.assertEqual(
            ArticleLink.objects.get(from_article=derived, to_article=base).kind,
            ArticleLink.KIND_SEE,
        )
        self.assertIn("kind не deriv", out.getvalue())

    def test_homonym_t_creates_deriv_link(self):
        a1 = Article.objects.create(word="kappaI", article_html="<b>kappaI</b>")
        a2 = Article.objects.create(word="kappaII", article_html="<b>kappaII</b>")
        ArticleIndexWord.objects.get_or_create(article=a1, word="kappa")
        ArticleIndexWord.objects.get_or_create(article=a2, word="kappa")
        src = Article.objects.create(
            word="kappas",
            article_html="<b>kappas</b> <i>freq</i> от kappa",
        )
        with patch(
            "dict.management.commands.fix_deriv_refs.Command._ask",
            return_value=f"t {a2.id}",
        ):
            call_command("fix_deriv_refs", "--queue", "homonym", stdout=StringIO())
        lnk = ArticleLink.objects.get(from_article=src, to_article=a2)
        self.assertEqual(lnk.kind, ArticleLink.KIND_DERIV)
        self.assertFalse(
            ArticleLink.objects.filter(from_article=src, to_article=a1).exists()
        )

    def test_dry_run_lists_targets(self):
        base = Article.objects.create(word="ruttoh", article_html="<b>ruttoh</b>")
        Article.objects.create(
            word="rutoldi",
            article_html="<b>rutoldi</b> <i>freq</i> от ruttoh",
        )
        out = StringIO()
        call_command(
            "fix_deriv_refs",
            "--apply-unique",
            "--dry-run",
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("rutoldi", text)
        self.assertIn("ruttoh", text)
        self.assertFalse(ArticleLink.objects.exists())
