from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ..helpers import sorted_by_krl
from ..models import Article, ArticleIndexTranslate
from ..translation_browser import (
    MODE_CONTAINS,
    MODE_EXACT,
    MODE_PREFIX,
    SORT_HIT,
    SORT_WORD,
    build_translation_cards,
    matching_translate_rows,
    normalize_sort,
)


class TranslationBrowserQueryTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.enzi = Article.objects.create(
            word="enzi|kandon'e",
            article_html="<b>enzi</b> первотельная (о корове)",
        )
        ArticleIndexTranslate.objects.create(
            article=cls.enzi, rus_word="первотельная (о корове)"
        )
        cls.decoy = Article.objects.create(
            word="baba",
            article_html="<b>baba</b> корова",
        )
        ArticleIndexTranslate.objects.create(article=cls.decoy, rus_word="корова")
        ArticleIndexTranslate.objects.create(article=cls.decoy, rus_word="бурёнка")
        cls.phrase = Article.objects.create(
            word="aiga",
            article_html="<b>aiga</b> дойная корова",
        )
        ArticleIndexTranslate.objects.create(
            article=cls.phrase, rus_word="дойная корова"
        )

    def test_exact_excludes_phrase_and_paren_gloss(self):
        ids = set(
            matching_translate_rows("корова", MODE_EXACT).values_list(
                "article_id", flat=True
            )
        )
        self.assertEqual(ids, {self.decoy.id})

    def test_exact_yo_to_e(self):
        ArticleIndexTranslate.objects.create(article=self.phrase, rus_word="мед")
        ids = set(
            matching_translate_rows("мёд", MODE_EXACT).values_list(
                "article_id", flat=True
            )
        )
        self.assertEqual(ids, {self.phrase.id})

    def test_contains_finds_phrase(self):
        # enzi has «корове» in parens — not substring «корова»
        ids = set(
            matching_translate_rows("корова", MODE_CONTAINS).values_list(
                "article_id", flat=True
            )
        )
        self.assertEqual(ids, {self.decoy.id, self.phrase.id})

    def test_prefix_match(self):
        ids = set(
            matching_translate_rows("дой", MODE_PREFIX).values_list(
                "article_id", flat=True
            )
        )
        self.assertEqual(ids, {self.phrase.id})

    def test_card_lists_all_translations_hits_first(self):
        cards = build_translation_cards("корова", MODE_EXACT)
        self.assertEqual(1, len(cards))
        card = cards[0]
        self.assertEqual(card.article.id, self.decoy.id)
        self.assertEqual(card.hit_translations, {"корова"})
        self.assertEqual(card.translations[0], "корова")
        # ё→е on save
        self.assertIn("буренка", card.translations)

    def test_exact_default_sort_is_word(self):
        self.assertEqual(SORT_WORD, normalize_sort(None, MODE_EXACT))

    def test_contains_default_sort_is_hit(self):
        self.assertEqual(SORT_HIT, normalize_sort(None, MODE_CONTAINS))

    def test_sort_by_hit_orders_cards(self):
        # decoy hit «корова», phrase hit «дойная корова» — «дойная…» before «корова»
        cards = build_translation_cards("корова", MODE_CONTAINS, sort=SORT_HIT)
        words = [c.article.word for c in cards]
        self.assertEqual(words[0], self.phrase.word)
        self.assertIn(self.decoy.word, words)

    def test_sort_by_word_uses_krl_order(self):
        cards = build_translation_cards("корова", MODE_CONTAINS, sort=SORT_WORD)
        expected = sorted(
            [c.article for c in cards],
            key=lambda a: (sorted_by_krl(a, "word"), a.pk),
        )
        self.assertEqual([c.article for c in cards], expected)


class TranslationBrowserAdminViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser("admin", "a@example.com", "x")
        cls.art = Article.objects.create(
            word="ruttoh",
            article_html="<b>ruttoh</b> быстро",
        )
        ArticleIndexTranslate.objects.create(article=cls.art, rus_word="быстро")
        ArticleIndexTranslate.objects.create(article=cls.art, rus_word="скоро")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("admin:dict_articleindextranslate_changelist")

    def test_changelist_requires_staff(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_empty_query_shows_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Введите русский перевод")
        self.assertNotContains(response, "ruttoh")

    def test_exact_query_shows_card(self):
        response = self.client.get(self.url, {"q": "быстро", "mode": "exact"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ruttoh")
        self.assertContains(response, "text-rus")
        self.assertContains(response, "быстро")
        self.assertContains(response, "скоро")
        self.assertContains(response, "править статью")

    def test_exact_miss_on_substring(self):
        response = self.client.get(self.url, {"q": "быстр", "mode": "exact"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ничего не найдено")

    def test_no_add_in_admin_index(self):
        from django.contrib import admin as dj_admin

        request = self.client.get("/admin/").wsgi_request
        request.user = self.user
        app_list = dj_admin.site.get_app_list(request)
        dict_app = next(a for a in app_list if a["app_label"] == "dict")
        names = [m["object_name"] for m in dict_app["models"]]
        self.assertIn("Article", names)
        self.assertIn("ArticleIndexTranslate", names)
        self.assertLess(names.index("Article"), names.index("ArticleIndexTranslate"))
        tr = next(
            m for m in dict_app["models"] if m["object_name"] == "ArticleIndexTranslate"
        )
        self.assertIsNone(tr.get("add_url"))
