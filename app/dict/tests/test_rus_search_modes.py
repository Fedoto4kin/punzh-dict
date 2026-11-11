"""View-level: explicit ?f=exact|all and bare-URL redirect for Russian search."""

from django.test import Client, TestCase

from ..models import Article, ArticleIndexTranslate, ArticleLink


class RusSearchModesViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        # Same cluster as SearchFilterTestCase — has exact hits.
        self.ruttoh = Article.objects.create(word="ruttoh")
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

        # Wide-only query: phrase token match, no rus_word == «первотельная».
        self.enzi = Article.objects.create(word="enzi")
        ArticleIndexTranslate.objects.create(
            article=self.enzi, rus_word="первотельная (о корове)"
        )

    def test_bare_url_redirects_to_exact_when_has_direct(self):
        response = self.client.get("/search/быстро", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("f=exact", response["Location"])

    def test_all_mode_renders_without_redirect_to_exact(self):
        response = self.client.get("/search/быстро/1?f=all", follow=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_f"], "all")
        self.assertTrue(response.context["has_direct"])
        self.assertTrue(response.context["refine_clickable"])
        self.assertEqual(response.context["found_count"], 4)  # no linkedown here

    def test_exact_mode_hides_refine_block(self):
        response = self.client.get("/search/быстро/1?f=exact", follow=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_f"], "exact")
        self.assertFalse(response.context["refine_clickable"])
        self.assertContains(response, "Точные результаты")
        self.assertContains(response, "Расширенный поиск")
        self.assertNotContains(response, "Уточнить запрос")

    def test_no_direct_redirects_to_all(self):
        response = self.client.get("/search/первотельная", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("f=all", response["Location"])
        followed = self.client.get(response["Location"])
        self.assertEqual(followed.status_code, 200)
        self.assertEqual(followed.context["active_f"], "all")
        self.assertFalse(followed.context["has_direct"])
        self.assertNotContains(followed, "Точные результаты")
