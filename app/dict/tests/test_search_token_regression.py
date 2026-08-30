"""Regression: Russian translate search uses whole-token OR, not FTS stem/substring."""

from django.test import TestCase

from ..models import Article, ArticleIndexTranslate
from ..search import search_by_translate_linked


class SearchTokenRegressionTestCase(TestCase):
    """Live-case replay: вон/там/вонь (backlog search after translation cleanup)."""

    @classmethod
    def setUpTestData(cls):
        cls.bare_tam = {}
        for word in ("siel'a", "siin'a", "tuala", "tuassa"):
            art = Article.objects.create(word=word)
            ArticleIndexTranslate.objects.create(article=art, rus_word="там")
            cls.bare_tam[word] = art

        cls.bare_von = {}
        for word in ("pois'", "ka", "kis"):
            art = Article.objects.create(word=word)
            ArticleIndexTranslate.objects.create(article=art, rus_word="вон")
            cls.bare_von[word] = art

        cls.tuola = Article.objects.create(word="tuola")
        ArticleIndexTranslate.objects.create(article=cls.tuola, rus_word="вон там")

        cls.tuuvalla = Article.objects.create(word="tuuvalla")
        ArticleIndexTranslate.objects.create(article=cls.tuuvalla, rus_word="вон там")

        cls.kuaru = Article.objects.create(word="kuaru")
        ArticleIndexTranslate.objects.create(article=cls.kuaru, rus_word="вонь")

        cls.haizu = Article.objects.create(word="haizu")
        ArticleIndexTranslate.objects.create(article=cls.haizu, rus_word="вонь")

        cls.zvon = Article.objects.create(word="hel'in'eh")
        ArticleIndexTranslate.objects.create(article=cls.zvon, rus_word="звон")

    def _article_ids(self, query, f=None):
        page, _, _, _ = search_by_translate_linked(query, 1, f)
        return {a.id for a in page.object_list}

    def test_tam_full_includes_bare_and_phrase(self):
        found = self._article_ids("там")
        for art in self.bare_tam.values():
            self.assertIn(art.id, found)
        self.assertIn(self.tuola.id, found)
        self.assertIn(self.tuuvalla.id, found)
        self.assertNotIn(self.kuaru.id, found)
        self.assertNotIn(self.haizu.id, found)
        self.assertNotIn(self.zvon.id, found)

    def test_tam_exact_only_bare_rows(self):
        found = self._article_ids("там", "exact")
        for art in self.bare_tam.values():
            self.assertIn(art.id, found)
        self.assertNotIn(self.tuola.id, found)
        self.assertNotIn(self.tuuvalla.id, found)

    def test_von_tam_full_or_anchor(self):
        found = self._article_ids("вон там")
        for art in self.bare_tam.values():
            self.assertIn(art.id, found)
        for art in self.bare_von.values():
            self.assertIn(art.id, found)
        self.assertIn(self.tuola.id, found)
        self.assertIn(self.tuuvalla.id, found)
        self.assertNotIn(self.kuaru.id, found)
        self.assertNotIn(self.haizu.id, found)
        self.assertNotIn(self.zvon.id, found)

    def test_von_tam_exact_only_phrase_rows(self):
        found = self._article_ids("вон там", "exact")
        self.assertEqual({self.tuola.id, self.tuuvalla.id}, found)

    def test_von_excludes_von_stench_and_zvon(self):
        found = self._article_ids("вон")
        for art in self.bare_von.values():
            self.assertIn(art.id, found)
        self.assertIn(self.tuola.id, found)
        self.assertIn(self.tuuvalla.id, found)
        self.assertNotIn(self.kuaru.id, found)
        self.assertNotIn(self.haizu.id, found)
        self.assertNotIn(self.zvon.id, found)
        for art in self.bare_tam.values():
            self.assertNotIn(art.id, found)

    def test_von_exact_only_bare_von(self):
        found = self._article_ids("вон", "exact")
        self.assertEqual({a.id for a in self.bare_von.values()}, found)
