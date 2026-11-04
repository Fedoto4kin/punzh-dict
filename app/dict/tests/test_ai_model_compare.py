import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from dict.ai.model_compare import (
    CANDIDATE_MODELS,
    PAGE_EXAMPLE_QUERIES,
    dedupe_models,
    model_roles,
    summarize_parse,
)
from dict.ai.query_parse import parse_query
from dict.management.commands.ai_query import BENCHMARKS_PATH
from dict.models import SemanticField


class BenchmarkFixtureTestCase(TestCase):
    def test_page_examples_are_in_the_fixture(self):
        cases = json.loads(BENCHMARKS_PATH.read_text(encoding="utf-8"))
        queries = {case["query"] for case in cases}
        missing = [query for query in PAGE_EXAMPLE_QUERIES if query not in queries]
        self.assertEqual(missing, [])


class ModelCompareScoreTestCase(TestCase):
    def test_dedupe_keeps_baseline_first(self):
        self.assertEqual(
            dedupe_models(
                ["yandex/yandexgpt-lite", *CANDIDATE_MODELS, "yandex/yandexgpt-lite"]
            ),
            ["yandex/yandexgpt-lite", *CANDIDATE_MODELS],
        )

    def test_roles_mark_current_query_that_is_also_cheap(self):
        self.assertEqual(
            model_roles(
                "xiaomi/mimo-v2.6-flash",
                query_model="xiaomi/mimo-v2.6-flash",
            ),
            ["разбор сейчас", "дешёвая"],
        )

    def test_parse_summary_lists_failures(self):
        summary = summarize_parse(
            [
                {"model": "m", "query": "корова", "ok": True, "latency_ms": 10},
                {
                    "model": "m",
                    "query": "da",
                    "ok": False,
                    "latency_ms": 20_000,
                    "over_prod_timeout": True,
                },
            ]
        )
        self.assertEqual(summary[0]["passed"], 1)
        self.assertEqual(summary[0]["failed"], ["da"])
        self.assertEqual(summary[0]["over_prod_timeout"], 1)


class ModelOverrideTestCase(TestCase):
    def setUp(self):
        SemanticField.objects.create(
            name="Животный мир", definition="животные", sorting=1
        )

    @override_settings(TIMEWEB_AI_MODEL_QUERY="yandex/yandexgpt-lite")
    @patch("dict.ai.query_parse.ai_client.chat_json")
    def test_parse_query_uses_explicit_model(self, mock_chat):
        mock_chat.return_value = {
            "lexical": ["коза"],
            "focus": [],
            "related": [],
            "fields": ["Животный мир"],
            "tags": [],
            "dialect": None,
            "dropped": [],
            "display": "коза",
        }
        parsed = parse_query("коза", model="zai/glm-4.7-flashx")
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["meta"]["model"], "zai/glm-4.7-flashx")
        self.assertEqual(mock_chat.call_args[0][2], "zai/glm-4.7-flashx")


class CompareCommandListTestCase(TestCase):
    def test_list_does_not_call_the_gateway(self):
        with patch("dict.ai.client.chat_json") as mock_chat:
            out = StringIO()
            call_command("compare_ai_models", "--list", stdout=out)
        mock_chat.assert_not_called()
        text = out.getvalue()
        self.assertIn("zai/glm-4.7-flashx", text)
        self.assertIn("примеры со страницы есть в эталонах", text)
        self.assertNotIn("реранк", text)
