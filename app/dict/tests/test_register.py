from unittest.mock import patch
from urllib.parse import quote, unquote

from django.test import Client, TestCase
from django.urls import reverse

from dict.helpers import normalization
from dict.models import Article, ArticleIndexTranslate
from dict.register import (
    RUS_ABC,
    build_register_rows,
    normalize_register_letter,
    register_content,
    register_letters_present,
)


class RegisterCoreTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.kissa = Article.objects.create(
            word="kissa", article_html="<b>kissa</b> кошка"
        )
        cls.kazi = Article.objects.create(word="kaži", article_html="<b>kaži</b> кошка")
        cls.aiga = Article.objects.create(
            word="aiga", article_html="<b>aiga</b> дикая кошка"
        )
        cls.purse = Article.objects.create(
            word="kukkaro", article_html="<b>kukkaro</b> кошелёк"
        )
        cls.spend = Article.objects.create(
            word="rašata", article_html="<b>rašata</b> раскошелиться"
        )
        cls.hedgehog = Article.objects.create(
            word="šiili", article_html="<b>šiili</b> ёж"
        )

        ArticleIndexTranslate.objects.create(article=cls.kissa, rus_word="кошка")
        ArticleIndexTranslate.objects.create(article=cls.kazi, rus_word="кошка")
        ArticleIndexTranslate.objects.create(article=cls.aiga, rus_word="дикая кошка")
        ArticleIndexTranslate.objects.create(article=cls.purse, rus_word="кошелёк")
        ArticleIndexTranslate.objects.create(
            article=cls.spend, rus_word="раскошелиться"
        )
        # Stored canonical: ё → е
        ArticleIndexTranslate.objects.create(article=cls.hedgehog, rus_word="ёж")

    def test_normalize_letter(self):
        self.assertEqual(normalize_register_letter("к"), "К")
        self.assertEqual(normalize_register_letter("ё"), "Е")
        self.assertIsNone(normalize_register_letter("Q"))
        self.assertIsNone(normalize_register_letter("АБ"))

    def test_group_same_rus_word(self):
        rows = build_register_rows("К", "")
        by_word = {r.rus_word: r for r in rows}
        self.assertIn("кошка", by_word)
        displays = [a.display for a in by_word["кошка"].articles]
        # Karelian order: kaži before kissa
        self.assertEqual(displays, [normalization("kaži"), normalization("kissa")])

    def test_letter_browse_excludes_other_letters(self):
        rows = build_register_rows("Д", "")
        words = [r.rus_word for r in rows]
        self.assertEqual(words, ["дикая кошка"])

    def test_prefix_word_start(self):
        rows = build_register_rows(None, "кош")
        words = {r.rus_word for r in rows}
        self.assertIn("кошка", words)
        self.assertIn("кошелек", words)  # canonical ё→е
        self.assertIn("дикая кошка", words)
        self.assertNotIn("раскошелиться", words)

    def test_prefix_yo_query(self):
        rows = build_register_rows(None, "ёж")
        words = [r.rus_word for r in rows]
        self.assertEqual(words, ["еж"])

    def test_multiword_or(self):
        # «дикая» OR prefix «кош» — both дикая кошка and кошка
        rows = build_register_rows(None, "дикая кош")
        words = {r.rus_word for r in rows}
        self.assertIn("дикая кошка", words)
        self.assertIn("кошка", words)

    def test_sorted_by_rus_alphabet(self):
        rows = build_register_rows(None, "кош")
        words = [r.rus_word for r in rows]
        self.assertEqual(words, sorted(words, key=lambda w: w.lower()))

    def test_search_urls(self):
        rows = build_register_rows("К", "")
        row = next(r for r in rows if r.rus_word == "кошка")
        self.assertIn("f=exact", row.search_url)
        self.assertTrue(row.search_url.startswith("/search/"))
        for a in row.articles:
            self.assertTrue(a.search_url.startswith("/search/"))
            self.assertNotIn("f=", a.search_url)

    def test_letters_present_skips_empty(self):
        letters = register_letters_present()
        self.assertIn("К", letters)
        self.assertIn("Д", letters)
        self.assertIn("Е", letters)  # ёж → е
        self.assertIn("Р", letters)
        self.assertNotIn("Й", letters)
        self.assertNotIn("А", letters)
        # Order follows RUS_ABC
        self.assertEqual(letters, "".join(c for c in RUS_ABC if c in letters))


class RegisterViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        art = Article.objects.create(word="kissa", article_html="<b>kissa</b>")
        ArticleIndexTranslate.objects.create(article=art, rus_word="кошка")
        art2 = Article.objects.create(word="kaži", article_html="<b>kaži</b>")
        ArticleIndexTranslate.objects.create(article=art2, rus_word="кошка")

    def setUp(self):
        self.c = Client()

    def test_root_redirects_to_first_present_letter(self):
        resp = self.c.get("/register/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(unquote(resp["Location"]), "/register/К/")

    def test_empty_letter_not_in_nav_and_404(self):
        resp = self.c.get(reverse("register_letter", kwargs={"letter": "К"}))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertNotIn(">Й<", content)
        self.assertNotIn("/register/Й/", content)
        resp_empty = self.c.get(reverse("register_letter", kwargs={"letter": "Й"}))
        self.assertEqual(resp_empty.status_code, 404)

    def test_letter_links_and_grouping_html(self):
        resp = self.c.get(reverse("register_letter", kwargs={"letter": "К"}))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("кошка", content)
        self.assertIn("?f=exact", content)
        # Both headwords linked without f= (ž may be percent-encoded)
        self.assertIn('href="/search/%s/1"' % quote("kaži", safe=""), content)
        self.assertIn('href="/search/kissa/1"', content)

    def test_query_filter(self):
        resp = self.c.get("/register/", {"q": "кош"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "кошка")

    def test_bad_letter_404(self):
        resp = self.c.get("/register/Q/")
        self.assertEqual(resp.status_code, 404)

    def test_nav_and_home_link(self):
        resp = self.c.get("/")
        self.assertContains(resp, 'href="%s"' % reverse("register"))
        self.assertContains(resp, "Регистр")

    def test_nav_active_only_register_not_alphabetic(self):
        # Register also passes letter=…; alphabetic index must not light up.
        resp = self.c.get(reverse("register_letter", kwargs={"letter": "К"}))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertRegex(
            content,
            r'class="dropdown-item\s+active"[^>]*>\s*Регистр',
        )
        self.assertNotRegex(
            content,
            r'class="dropdown-item\s+active"[^>]*>\s*Алфавитный указатель',
        )

    def test_rus_abc_constant(self):
        self.assertTrue(RUS_ABC.startswith("АБВ"))
        self.assertNotIn("Ё", RUS_ABC)
        self.assertNotIn("Ъ", RUS_ABC)
        self.assertNotIn("Ы", RUS_ABC)

    def test_register_content_empty_letter(self):
        content = register_content(letter="Щ", page=1, query="")
        self.assertEqual(content.page_obj.paginator.count, 0)
        self.assertEqual(content.letter, "Щ")
        self.assertNotIn("Щ", content.letters)

    def test_pagination_ellipsis_on_gap(self):
        # 1 existing «кошка» + 9 more → 10 pages at 1 row/page; gap → …
        art = Article.objects.create(word="pad")
        for i in range(9):
            ArticleIndexTranslate.objects.create(article=art, rus_word="каша%02d" % i)
        with patch("dict.register.ROWS_PER_PAGE", 1):
            resp = self.c.get(reverse("register_letter", kwargs={"letter": "К"}))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn("&hellip;", html)
        self.assertIn('aria-hidden="true"', html)
        self.assertIn(">10</a>", html)
