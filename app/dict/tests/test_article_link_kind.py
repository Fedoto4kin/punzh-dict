from django.test import TestCase

from dict.models import Article, ArticleLink
from dict.see_audit import infer_link_kind


class InferLinkKindTestCase(TestCase):
    def test_see_from_sm_marker(self):
        donor = Article.objects.create(word="ruttoh", article_html="<b>ruttoh</b>")
        stub = Article.objects.create(
            word="rutoldi",
            article_html="<b>rutoldi</b> <i>см.</i> ruttoh",
        )
        self.assertEqual(infer_link_kind(stub, donor), ArticleLink.KIND_SEE)

    def test_cf_from_sr_marker(self):
        donor = Article.objects.create(word="naine", article_html="<b>naine</b>")
        stub = Article.objects.create(
            word="akka",
            article_html="<b>akka</b> <i>ср.</i> naine",
        )
        self.assertEqual(infer_link_kind(stub, donor), ArticleLink.KIND_CF)

    def test_cf_in_comma_list(self):
        a = Article.objects.create(word="merluwga", article_html="<b>merluwga</b>")
        b = Article.objects.create(word="pahna", article_html="<b>pahna</b>")
        stub = Article.objects.create(
            word="berluwga",
            article_html="<b>berluwga</b> <i>ср.</i> merluwga, pahna",
        )
        self.assertEqual(infer_link_kind(stub, a), ArticleLink.KIND_CF)
        self.assertEqual(infer_link_kind(stub, b), ArticleLink.KIND_CF)

    def test_deriv_from_freq_tag(self):
        base = Article.objects.create(
            word="abewttua", article_html="<b>abewttua</b> глаг."
        )
        derived = Article.objects.create(
            word="abewt||ella",
            article_html="<b>abewt||ella</b> <i>freq</i> от abewttua",
        )
        self.assertEqual(infer_link_kind(derived, base), ArticleLink.KIND_DERIV)

    def test_deriv_loose(self):
        base = Article.objects.create(word="armaštua", article_html="<b>armaštua</b>")
        derived = Article.objects.create(
            word="armaššuš",
            article_html="<b>armaššuš</b> от armaštua",
        )
        self.assertEqual(infer_link_kind(derived, base), ArticleLink.KIND_DERIV)

    def test_default_see_when_no_html_match(self):
        a = Article.objects.create(word="aaa", article_html="<b>aaa</b> foo")
        b = Article.objects.create(word="bbb", article_html="<b>bbb</b> bar")
        self.assertEqual(infer_link_kind(a, b), ArticleLink.KIND_SEE)
