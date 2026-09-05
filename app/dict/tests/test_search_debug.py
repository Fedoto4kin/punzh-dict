from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ..models import Article, ArticleIndexTranslate, ArticleLink
from ..search import search_by_translate_linked
from ..search_debug import explain_rus_search, prepare_rus_debug_query


class PrepareRusDebugQueryTestCase(TestCase):
    def test_yo_to_e(self):
        self.assertEqual("мед", prepare_rus_debug_query("мёд"))

    def test_strip(self):
        self.assertEqual("быстро", prepare_rus_debug_query("  быстро  "))


class ExplainRusSearchTestCase(TestCase):
    """Same cluster as test_search_filter — reasons must match pipeline layers."""

    def setUp(self):
        self.ruttoh = Article.objects.create(
            word="ruttoh", article_html="<b>ruttoh</b> быстро"
        )
        for rw in ["быстро", "круто", "скоро"]:
            ArticleIndexTranslate.objects.create(article=self.ruttoh, rus_word=rw)

        self.maihahtua = Article.objects.create(word="maihahtua")
        for rw in ["быстро", "быстро пробежать"]:
            ArticleIndexTranslate.objects.create(article=self.maihahtua, rus_word=rw)

        self.ehatta = Article.objects.create(word="ehatta")
        ArticleIndexTranslate.objects.create(
            article=self.ehatta, rus_word="быстро ехать"
        )

        self.rutoldi = Article.objects.create(word="rutoldi")
        ArticleLink.objects.create(from_article=self.rutoldi, to_article=self.ruttoh)

        self.linkedown = Article.objects.create(word="linkedown")
        ArticleIndexTranslate.objects.create(
            article=self.linkedown, rus_word="медленно"
        )
        ArticleLink.objects.create(from_article=self.linkedown, to_article=self.ruttoh)

    def _by_word(self, result):
        return {c.article.word: c for c in result.cards}

    def test_counts_match_public_search(self):
        page_obj, found_count, narrowing, direct_ids, related = (
            search_by_translate_linked("быстро", 1, None)
        )
        result = explain_rus_search("быстро")
        self.assertEqual(found_count, result.found_count)
        self.assertEqual(set(direct_ids), result.direct_ids)
        self.assertEqual(related, result.related_queries)
        self.assertEqual(
            {t["key"] for t in narrowing}, {t["key"] for t in result.narrowing}
        )

    def test_ilike_and_exact_badges(self):
        result = explain_rus_search("быстро")
        cards = self._by_word(result)
        codes = {r.code for r in cards["ruttoh"].reasons}
        self.assertIn("ilike", codes)
        self.assertIn("exact", codes)
        self.assertIn("быстро", cards["ruttoh"].matched_translations)

    def test_token_badge_on_phrase(self):
        result = explain_rus_search("быстро")
        cards = self._by_word(result)
        codes = {r.code for r in cards["ehatta"].reasons}
        self.assertIn("token", codes)
        self.assertNotIn("exact", codes)
        self.assertIn("быстро ехать", cards["ehatta"].matched_translations)

    def test_link_only_with_via(self):
        result = explain_rus_search("быстро")
        cards = self._by_word(result)
        link = cards["linkedown"]
        codes = {r.code for r in link.reasons}
        self.assertIn("link", codes)
        self.assertNotIn("ilike", codes)
        self.assertNotIn("token", codes)
        via_words = {v["word"] for r in link.reasons if r.code == "link" for v in r.via}
        self.assertIn("ruttoh", via_words)

    def test_inherited_exact(self):
        result = explain_rus_search("быстро")
        cards = self._by_word(result)
        exact = [r for r in cards["rutoldi"].reasons if r.code == "exact"]
        self.assertTrue(exact)
        self.assertTrue(exact[0].inherited)

    def test_exact_filter_page(self):
        result = explain_rus_search("быстро", f="exact")
        words = {c.article.word for c in result.cards}
        self.assertEqual(words, {"ruttoh", "rutoldi", "maihahtua"})

    def test_fuzzy_token_reason(self):
        enzi = Article.objects.create(word="enzi|kandon'e")
        ArticleIndexTranslate.objects.create(
            article=enzi, rus_word="первотельная (о корове)"
        )
        result = explain_rus_search("корова")
        cards = self._by_word(result)
        self.assertIn("enzi|kandon'e", cards)
        token = [r for r in cards["enzi|kandon'e"].reasons if r.code == "token"]
        self.assertTrue(token)
        self.assertTrue(token[0].fuzzy)


class SearchDebugAdminViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser("admin", "a@example.com", "x")
        cls.art = Article.objects.create(
            word="ruttoh", article_html="<b>ruttoh</b> быстро"
        )
        ArticleIndexTranslate.objects.create(article=cls.art, rus_word="быстро")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("admin:dict_article_search_debug")

    def test_requires_staff(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_empty_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Русский запрос")

    def test_query_shows_badges(self):
        response = self.client.get(self.url, {"q": "быстро"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ruttoh")
        self.assertContains(response, "sd-badge--ilike")
        self.assertContains(response, "равенство")
