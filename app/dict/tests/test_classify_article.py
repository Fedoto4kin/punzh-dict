from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from dict.ai.classify import CLASSIFY_TIMEOUT, classify_article, sanitize_keyword
from dict.ai.prompts import (
    SYSTEM_PROMPT_FROZEN,
    build_article_input,
    cyrillic_from_html,
)
from dict.models import (
    Article,
    ArticleIndexTranslate,
    ArticleKeyword,
    ArticleSemanticField,
    SemanticField,
)


class SanitizeKeywordTestCase(TestCase):
    def test_drops_short_and_numeric(self):
        self.assertIsNone(sanitize_keyword("a"))
        self.assertIsNone(sanitize_keyword("123"))
        self.assertIsNone(sanitize_keyword("  "))
        self.assertEqual("лиса", sanitize_keyword("  Лиса  "))


class PromptsTestCase(TestCase):
    def test_cyrillic_from_html_strips_tags(self):
        html = "<i>см.</i> лиса рыжая в лесу"
        found = cyrillic_from_html(html)
        self.assertTrue(any("лиса" in c.lower() for c in found))

    def test_article_input_subtracts_translations(self):
        art = Article.objects.create(
            word="reboi", article_html="лиса рыжая; в лесу живёт"
        )
        ArticleIndexTranslate.objects.create(article=art, rus_word="лиса")
        payload = build_article_input(art)
        self.assertEqual(payload["word"], "reboi")
        self.assertEqual(payload["translations"], ["лиса"])
        self.assertTrue(all("лиса" != c.lower() for c in payload["illustrations_ru"]))


class ClassifyArticleTestCase(TestCase):
    def setUp(self):
        self.animals = SemanticField.objects.create(
            name="Животный мир",
            definition="звери и птицы",
            sorting=1,
        )
        self.food = SemanticField.objects.create(
            name="Пища и напитки",
            definition="еда",
            sorting=2,
        )
        self.art = Article.objects.create(word="reboi", article_html="лиса рыжая")
        ArticleIndexTranslate.objects.create(article=self.art, rus_word="лиса")
        self.other = Article.objects.create(word="leibä")
        ArticleSemanticField.objects.create(article=self.other, field=self.food)
        ArticleKeyword.objects.create(article=self.other, word="хлеб")

    def _ok_payload(self, **overrides):
        data = {
            "keywords": ["Лиса", "a", "123", "лиса"],
            "fields": ["Животный мир", "несуществующее", "Пища и напитки"],
            "no_field": False,
        }
        data.update(overrides)
        return data

    def test_missing_article(self):
        result = classify_article(999999)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "not_found")
        self.assertFalse(result["persisted"])

    def test_empty_ontology_does_not_call_llm(self):
        SemanticField.objects.all().delete()
        with patch("dict.ai.client.chat_json") as mock_chat:
            result = classify_article(self.art.id)
        mock_chat.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "empty_ontology")

    def test_llm_none_does_not_write(self):
        with patch("dict.ai.client.chat_json", return_value=None):
            result = classify_article(self.art.id)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "llm_unavailable")
        self.assertFalse(self.art.semantic_assignments.exists())
        self.assertFalse(ArticleKeyword.objects.filter(article=self.art).exists())

    def test_persists_filtered_fields_and_sanitized_keywords(self):
        captured = {}

        def fake_chat(system, user, model, timeout=10):
            captured["system"] = system
            captured["user"] = user
            captured["model"] = model
            captured["timeout"] = timeout
            return self._ok_payload()

        with patch("dict.ai.client.chat_json", side_effect=fake_chat):
            result = classify_article(self.art.id)

        self.assertTrue(result["ok"])
        self.assertTrue(result["persisted"])
        self.assertEqual(result["fields"], ["Животный мир", "Пища и напитки"])
        self.assertEqual(result["keywords"], ["лиса"])
        self.assertEqual(captured["system"], SYSTEM_PROMPT_FROZEN)
        self.assertIn("Животный мир", captured["user"])
        self.assertIn("Пища и напитки", captured["user"])
        self.assertEqual(captured["timeout"], CLASSIFY_TIMEOUT)
        self.assertEqual(captured["model"], settings.TIMEWEB_AI_MODEL_CLASSIFY)
        names = list(
            self.art.semantic_assignments.order_by("field__sorting").values_list(
                "field__name", flat=True
            )
        )
        self.assertEqual(names, ["Животный мир", "Пища и напитки"])
        self.assertFalse(
            self.art.semantic_assignments.filter(from_translation=True).exists()
        )
        self.assertEqual(
            list(
                ArticleKeyword.objects.filter(article=self.art).values_list(
                    "word", flat=True
                )
            ),
            ["лиса"],
        )
        # other article untouched
        self.assertTrue(
            self.other.semantic_assignments.filter(field=self.food).exists()
        )
        self.assertTrue(
            ArticleKeyword.objects.filter(article=self.other, word="хлеб").exists()
        )

    def test_replaces_existing_assignments(self):
        ArticleSemanticField.objects.create(article=self.art, field=self.food)
        ArticleKeyword.objects.create(article=self.art, word="старое")
        with patch(
            "dict.ai.client.chat_json",
            return_value={
                "keywords": ["лиса"],
                "fields": ["Животный мир"],
                "no_field": False,
            },
        ):
            classify_article(self.art.id)
        names = list(
            self.art.semantic_assignments.values_list("field__name", flat=True)
        )
        self.assertEqual(names, ["Животный мир"])
        self.assertEqual(
            list(
                ArticleKeyword.objects.filter(article=self.art).values_list(
                    "word", flat=True
                )
            ),
            ["лиса"],
        )

    def test_no_field_still_writes_keywords(self):
        with patch(
            "dict.ai.client.chat_json",
            return_value={
                "keywords": ["частица"],
                "fields": [],
                "no_field": True,
            },
        ):
            result = classify_article(self.art.id)
        self.assertTrue(result["ok"])
        self.assertTrue(result["no_field"])
        self.assertFalse(self.art.semantic_assignments.exists())
        self.assertEqual(
            list(
                ArticleKeyword.objects.filter(article=self.art).values_list(
                    "word", flat=True
                )
            ),
            ["частица"],
        )

    def test_dry_run_does_not_write(self):
        with patch(
            "dict.ai.client.chat_json",
            return_value=self._ok_payload(),
        ):
            result = classify_article(self.art.id, persist=False)
        self.assertTrue(result["ok"])
        self.assertFalse(result["persisted"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["fields"], ["Животный мир", "Пища и напитки"])
        self.assertFalse(self.art.semantic_assignments.exists())

    def test_management_command_writes(self):
        with patch(
            "dict.ai.client.chat_json",
            return_value={
                "keywords": ["лиса"],
                "fields": ["Животный мир"],
                "no_field": False,
            },
        ):
            out = StringIO()
            call_command("classify_article", "--id", str(self.art.id), stdout=out)
        self.assertIn("Животный мир", out.getvalue())
        self.assertTrue(
            self.art.semantic_assignments.filter(field=self.animals).exists()
        )

    def test_management_command_missing_id_raises(self):
        with self.assertRaises(CommandError):
            call_command("classify_article", "--id", "999999")

    def test_management_command_dry_run(self):
        with patch(
            "dict.ai.client.chat_json",
            return_value=self._ok_payload(),
        ):
            out = StringIO()
            call_command(
                "classify_article",
                "--id",
                str(self.art.id),
                "--dry-run",
                stdout=out,
            )
        self.assertIn("dry-run", out.getvalue())
        self.assertFalse(self.art.semantic_assignments.exists())
