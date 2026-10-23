from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from dict.models import (
    Article,
    ArticleIndexTranslate,
    ArticleSemanticField,
    SemanticField,
)


class AiSearchViewTestCase(TestCase):
    def setUp(self):
        self.field = SemanticField.objects.create(
            name="Животный мир", definition="животные", sorting=1
        )
        self.art = Article.objects.create(word="kaza", article_html="<b>kaza</b>")
        ArticleIndexTranslate.objects.create(article=self.art, rus_word="коза")
        ArticleSemanticField.objects.create(article=self.art, field=self.field)

    def test_empty_form(self):
        resp = self.client.get(reverse("ai_search"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Умный поиск")
        self.assertContains(resp, 'name="query"')

    @patch("dict.ai.query_parse.parse_query")
    def test_grouped_results(self, mock_parse):
        mock_parse.return_value = {
            "ok": True,
            "parse_ok": True,
            "query": "коза",
            "lexical": ["коза"],
            "focus": [],
            "related": [],
            "fields": ["Животный мир"],
            "tags": [],
            "dialect": None,
            "dropped": [],
            "display": "искали: коза",
            "warnings": [],
            "raw": {},
            "error": None,
            "meta": {},
        }
        resp = self.client.get(reverse("ai_search"), {"query": "коза"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "искали: коза")
        self.assertContains(resp, "kaza")
        self.assertContains(resp, "card-body")
        self.assertContains(resp, "буквально")
        mock_parse.assert_called()

    @patch("dict.ai.query_parse.parse_query")
    def test_fallback_message(self, mock_parse):
        mock_parse.return_value = {
            "ok": False,
            "parse_ok": False,
            "query": "коза",
            "lexical": [],
            "focus": [],
            "related": [],
            "fields": [],
            "tags": [],
            "dialect": None,
            "dropped": [],
            "display": "",
            "warnings": [],
            "raw": None,
            "error": "llm_unavailable",
            "meta": {},
        }
        resp = self.client.get(reverse("ai_search"), {"query": "коза"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "По смыслу не нашли")
        self.assertContains(resp, "kaza")
