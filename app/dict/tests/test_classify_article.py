from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from dict.ai.classify import classify_article, sanitize_keyword
from dict.ai.prompts import (
    SYSTEM_PROMPT_FROZEN,
    SYSTEM_PROMPT_TRANSLATION_FIELDS,
    build_article_input,
    cyrillic_from_html,
    translations_for_classification,
)
from dict.models import (
    Article,
    ArticleAddition,
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

    def test_article_input_includes_addendum_illustrations(self):
        art = Article.objects.create(word="lemma", article_html="<b>w</b> основной")
        ArticleAddition.objects.create(
            article=art,
            article_html="<b>w</b> <i>v</i> второе значение; karel t'ext",
        )
        payload = build_article_input(art)
        self.assertTrue(
            any("второе значение" in c for c in payload["illustrations_ru"])
        )

    def test_translations_for_classification_uses_index_not_html(self):
        art = Article.objects.create(word="lemma", article_html="<b>w</b> one")
        ArticleIndexTranslate.objects.create(article=art, rus_word="из индекса")
        ArticleAddition.objects.create(
            article=art,
            article_html="<b>w</b> <i>v</i> дополнительный перевод",
        )
        trs = translations_for_classification(art)
        self.assertEqual(trs, ["из индекса"])


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

    def _translation_payload(self, **overrides):
        data = {"translation_fields": ["Животный мир"]}
        data.update(overrides)
        return data

    def _mock_chat(self, classify_payload=None, translation_payload=None):
        classify_payload = classify_payload or self._ok_payload()
        translation_payload = translation_payload or self._translation_payload()

        def fake_chat(system, user, model, timeout=10):
            if system == SYSTEM_PROMPT_FROZEN:
                return classify_payload
            if system == SYSTEM_PROMPT_TRANSLATION_FIELDS:
                return translation_payload
            return None

        return fake_chat

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
        captured = []

        def fake_chat(system, user, model, timeout=10):
            captured.append({"system": system, "user": user, "model": model})
            if system == SYSTEM_PROMPT_FROZEN:
                return self._ok_payload()
            return self._translation_payload(
                translation_fields=["Животный мир", "Пища и напитки"]
            )

        with patch("dict.ai.client.chat_json", side_effect=fake_chat):
            result = classify_article(self.art.id)

        self.assertTrue(result["ok"])
        self.assertTrue(result["persisted"])
        self.assertEqual(result["fields"], ["Животный мир", "Пища и напитки"])
        self.assertEqual(
            result["translation_fields"], ["Животный мир", "Пища и напитки"]
        )
        self.assertEqual(result["keywords"], ["лиса"])
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0]["system"], SYSTEM_PROMPT_FROZEN)
        self.assertEqual(captured[1]["system"], SYSTEM_PROMPT_TRANSLATION_FIELDS)
        self.assertIn("Животный мир", captured[0]["user"])
        self.assertEqual(captured[0]["model"], settings.TIMEWEB_AI_MODEL_CLASSIFY)
        names = list(
            self.art.semantic_assignments.order_by("field__sorting").values_list(
                "field__name", flat=True
            )
        )
        self.assertEqual(names, ["Животный мир", "Пища и напитки"])
        self.assertTrue(
            self.art.semantic_assignments.get(field=self.animals).from_translation
        )
        self.assertTrue(
            self.art.semantic_assignments.get(field=self.food).from_translation
        )
        self.assertEqual(
            list(
                ArticleKeyword.objects.filter(article=self.art).values_list(
                    "word", flat=True
                )
            ),
            ["лиса"],
        )
        self.assertTrue(
            self.other.semantic_assignments.filter(field=self.food).exists()
        )

    def test_translation_fields_failure_still_persists_with_false_flags(self):
        def fake_chat(system, user, model, timeout=10):
            if system == SYSTEM_PROMPT_FROZEN:
                return self._ok_payload()
            return None

        with patch("dict.ai.client.chat_json", side_effect=fake_chat):
            result = classify_article(self.art.id)

        self.assertTrue(result["ok"])
        self.assertEqual(result["error"], "translation_fields_unavailable")
        self.assertEqual(result["translation_fields"], [])
        self.assertFalse(
            self.art.semantic_assignments.filter(from_translation=True).exists()
        )

    def test_skips_second_call_when_no_fields(self):
        with patch("dict.ai.client.chat_json") as mock_chat:
            mock_chat.return_value = {
                "keywords": ["частица"],
                "fields": [],
                "no_field": True,
            }
            result = classify_article(self.art.id)
        self.assertEqual(mock_chat.call_count, 1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["translation_fields"], [])

    def test_replaces_existing_assignments(self):
        ArticleSemanticField.objects.create(article=self.art, field=self.food)
        ArticleKeyword.objects.create(article=self.art, word="старое")
        with patch(
            "dict.ai.client.chat_json",
            side_effect=self._mock_chat(
                classify_payload={
                    "keywords": ["лиса"],
                    "fields": ["Животный мир"],
                    "no_field": False,
                },
                translation_payload={"translation_fields": ["Животный мир"]},
            ),
        ):
            classify_article(self.art.id)
        names = list(
            self.art.semantic_assignments.values_list("field__name", flat=True)
        )
        self.assertEqual(names, ["Животный мир"])
        self.assertTrue(
            self.art.semantic_assignments.get(field=self.animals).from_translation
        )
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
            side_effect=self._mock_chat(),
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
            side_effect=self._mock_chat(
                classify_payload={
                    "keywords": ["лиса"],
                    "fields": ["Животный мир"],
                    "no_field": False,
                },
                translation_payload={"translation_fields": ["Животный мир"]},
            ),
        ):
            out = StringIO()
            call_command("classify_article", "--id", str(self.art.id), stdout=out)
        self.assertIn("Животный мир", out.getvalue())
        self.assertIn("по переводу", out.getvalue())
        self.assertTrue(
            self.art.semantic_assignments.filter(field=self.animals).exists()
        )

    def test_management_command_missing_id_raises(self):
        with self.assertRaises(CommandError):
            call_command("classify_article", "--id", "999999")

    def test_management_command_dry_run(self):
        with patch(
            "dict.ai.client.chat_json",
            side_effect=self._mock_chat(),
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
