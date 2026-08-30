from django.test import TestCase

from ..models import Article, ArticleLink
from ..search import expand_by_links, sort_and_paginate


# NOTE: these are DB-backed (TestCase, not SimpleTestCase). Each
# Article.objects.create() triggers the Article.save() override, which rebuilds
# the word-index tables — a cost, not a correctness concern here. The
# ArticleIndexTranslate post_save signal is NOT exercised: neither function
# under test touches translations.


class SortAndPaginateTestCase(TestCase):
    """
    Covers what the pagination-hints tests could not: the actual order/
    composition/count produced by the shared sort_and_paginate primitive.
    Also doubles as the missing "sorting by Krl" coverage (see the TODO in
    test_helpers.py).
    """

    def test_orders_by_karelian_collation(self):
        # Inserted deliberately out of order. Expected Krl-collated order is
        # aiga < muše < šoba (M=13 < S=18 < Š=19 in KRL_ABC).
        for w in ["šoba", "aiga", "muše"]:
            Article.objects.create(word=w)

        page_obj, sorted_articles = sort_and_paginate(Article.objects.all(), 1)

        self.assertEqual(["aiga", "muše", "šoba"], [a.word for a in page_obj])
        self.assertEqual(["aiga", "muše", "šoba"], [a.word for a in sorted_articles])
        self.assertEqual(3, page_obj.paginator.count)

    def test_empty_input(self):
        # No articles: valid empty page, count 0, no crash.
        page_obj, sorted_articles = sort_and_paginate(Article.objects.none(), 1)

        self.assertEqual([], list(page_obj))
        self.assertEqual([], sorted_articles)
        self.assertEqual(0, page_obj.paginator.count)


class ExpandByLinksTestCase(TestCase):
    """
    Pins the bidirectional cluster expansion introduced with ArticleLink —
    the behaviour the translation-search fix depends on.
    """

    def setUp(self):
        self.a = Article.objects.create(word="aiga")
        self.b = Article.objects.create(word="muše")
        self.c = Article.objects.create(word="šoba")
        # Only one direction is stored: A -> B.
        ArticleLink.objects.create(from_article=self.a, to_article=self.b)

    def test_expands_both_directions(self):
        # Forward (outgoing): querying A pulls B.
        self.assertEqual({self.a.id, self.b.id}, expand_by_links([self.a.id]))
        # Reverse (incoming): querying B pulls A even though only A -> B exists.
        # This is exactly what the old one-directional lookup missed.
        self.assertEqual({self.a.id, self.b.id}, expand_by_links([self.b.id]))

    def test_unlinked_article_not_pulled(self):
        # C has no links: it maps only to itself, and no cluster leaks in.
        self.assertEqual({self.c.id}, expand_by_links([self.c.id]))

    def test_cf_link_not_expanded(self):
        cf = Article.objects.create(word="cfword")
        ArticleLink.objects.create(
            from_article=cf, to_article=self.a, kind=ArticleLink.KIND_CF
        )
        self.assertEqual({cf.id}, expand_by_links([cf.id]))
        expanded_from_a = expand_by_links([self.a.id])
        self.assertNotIn(cf.id, expanded_from_a)
        self.assertIn(self.b.id, expanded_from_a)

    def test_deriv_link_expanded(self):
        deriv = Article.objects.create(word="rutoldi")
        ArticleLink.objects.create(
            from_article=deriv, to_article=self.a, kind=ArticleLink.KIND_DERIV
        )
        self.assertEqual({deriv.id, self.a.id}, expand_by_links([deriv.id]))
        expanded_from_a = expand_by_links([self.a.id])
        self.assertIn(deriv.id, expanded_from_a)
        self.assertIn(self.b.id, expanded_from_a)
