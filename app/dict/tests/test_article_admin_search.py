from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import NoReverseMatch, reverse

from ..admin import ArticleAdm
from ..models import Article
from ..search import prepare_krl_ilike_query


class PrepareKrlIlikeQueryTestCase(SimpleTestCase):
    def test_question_is_any_sequence(self):
        self.assertEqual("ai%", prepare_krl_ilike_query("ai?"))

    def test_dot_is_one_character(self):
        self.assertEqual("ai_", prepare_krl_ilike_query("ai."))

    def test_diacritics_fold(self):
        self.assertEqual("soba", prepare_krl_ilike_query("šoba"))


class ArticleAdminKrlSearchTestCase(TestCase):
    def setUp(self):
        self.admin = ArticleAdm(Article, AdminSite())
        self.factory = RequestFactory()
        self.user = User.objects.create_superuser("admin", "a@example.com", "x")
        self.aiga = Article.objects.create(word="aiga")
        self.aika = Article.objects.create(word="aika")
        self.aia = Article.objects.create(word="aia")
        self.baba = Article.objects.create(word="baba")

    def _ids(self, term, path="/admin/dict/article/"):
        request = self.factory.get(path)
        request.user = self.user
        qs, _ = self.admin.get_search_results(request, Article.objects.all(), term)
        return set(qs.values_list("word", flat=True))

    def test_exact_headword(self):
        self.assertEqual(self._ids("aiga"), {"aiga"})

    def test_question_matches_any_tail(self):
        self.assertEqual(self._ids("ai?"), {"aiga", "aika", "aia"})

    def test_dot_matches_one_character(self):
        self.assertEqual(self._ids("ai."), {"aia"})

    def test_empty_changelist_keeps_all(self):
        self.assertEqual(len(self._ids("")), 4)

    def test_empty_autocomplete_returns_none(self):
        self.assertEqual(
            self._ids("", path="/admin/autocomplete/"),
            set(),
        )

    def test_change_form_uses_autocomplete_widget(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/admin/dict/article/{self.aiga.pk}/change/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("admin-autocomplete", html)
        self.assertIn("to_article", html)

    def test_changelist_query_uses_krl_wildcards(self):
        self.client.force_login(self.user)
        response = self.client.get("/admin/dict/article/", {"q": "ai."})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(">aia<", html)
        self.assertNotIn(">aiga<", html)
        self.assertNotIn(">baba<", html)

    def test_changelist_is_not_substring_on_word(self):
        # Django default search_fields icontains would match aiga/aika/aia
        # for q=ai; Karelian ILIKE without ?/. is exact on the word index.
        self.client.force_login(self.user)
        response = self.client.get("/admin/dict/article/", {"q": "ai"})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(">aiga<", html)
        self.assertNotIn(">aika<", html)
        self.assertNotIn(">aia<", html)

    def test_autocomplete_json_respects_wildcards(self):
        self.client.force_login(self.user)
        try:
            url = reverse("admin:autocomplete")
        except NoReverseMatch:
            url = reverse("admin:dict_article_autocomplete")
        response = self.client.get(
            url,
            {
                "term": "ai.",
                "app_label": "dict",
                "model_name": "articlelink",
                "field_name": "to_article",
            },
        )
        self.assertEqual(response.status_code, 200)
        texts = {row["text"] for row in response.json()["results"]}
        self.assertEqual(texts, {"aia"})
