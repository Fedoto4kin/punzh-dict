import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from dict.models import (
    AiSearchJob,
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
        self.assertContains(resp, "ai-search/jobs/")

    def test_shell_does_not_call_llm(self):
        with patch("dict.ai.query_parse.parse_query") as mock_parse:
            resp = self.client.get(reverse("ai_search"), {"query": "коза"})
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "ai-pending-query")
            self.assertContains(resp, "нужен JavaScript")
            mock_parse.assert_not_called()


class AiSearchJobApiTestCase(TestCase):
    def setUp(self):
        self.field = SemanticField.objects.create(
            name="Животный мир", definition="животные", sorting=1
        )
        self.art = Article.objects.create(word="kaza", article_html="<b>kaza</b>")
        ArticleIndexTranslate.objects.create(article=self.art, rus_word="коза")
        ArticleSemanticField.objects.create(article=self.art, field=self.field)

    def _parsed_ok(self):
        return {
            "ok": True,
            "parse_ok": True,
            "query": "коза",
            "lexical": ["коза"],
            "focus": [],
            "related": [],
            "fields": ["Животный мир"],
            "tags": [],
            "place": None,
            "dialect": None,
            "dropped": [],
            "display": "искали: коза",
            "krl_headword": False,
            "warnings": [],
            "error": None,
        }

    def test_create_and_poll_done(self):
        from dict.ai.jobs import run_job

        mock_parsed = self._parsed_ok()
        self.client.session.save()

        with patch("dict.ai.jobs.schedule_ai_search_job", return_value=True):
            resp = self.client.post(
                reverse("ai_search_job_create"),
                data=json.dumps({"query": "коза", "sort": "relevance"}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 202)
        job_id = resp.json()["id"]
        job = AiSearchJob.objects.get(pk=job_id)
        self.assertEqual(job.status, AiSearchJob.STATUS_QUEUED)

        with patch("dict.ai.query_parse.parse_query", return_value=mock_parsed):
            run_job(job_id)
        job.refresh_from_db()
        self.assertEqual(job.status, AiSearchJob.STATUS_DONE)
        self.assertTrue(job.groups)

        st = self.client.get(reverse("ai_search_job_status", args=[job_id]))
        self.assertEqual(st.status_code, 200)
        self.assertEqual(st.json()["status"], "done")
        self.assertEqual(st.json()["parsed"]["display"], "искали: коза")
        fields = st.json().get("ontology_fields") or []
        self.assertTrue(fields)
        self.assertEqual(fields[0]["name"], "Животный мир")
        self.assertIn("id", fields[0])

        partial = self.client.get(reverse("ai_search_job_partial", args=[job_id]))
        self.assertEqual(partial.status_code, 200)
        self.assertContains(partial, "kaza")
        self.assertContains(partial, "card-body")

        page = self.client.get(reverse("ai_search"), {"job": job_id})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "искали: коза")
        self.assertContains(page, "kaza")

    def test_sort_switch_reuses_job_without_llm(self):
        from dict.ai.jobs import run_job

        mock_parsed = self._parsed_ok()
        with patch("dict.ai.jobs.schedule_ai_search_job", return_value=True):
            resp = self.client.post(
                reverse("ai_search_job_create"),
                data=json.dumps({"query": "коза", "sort": "relevance"}),
                content_type="application/json",
            )
        job_id = resp.json()["id"]
        with patch("dict.ai.query_parse.parse_query", return_value=mock_parsed):
            run_job(job_id)

        with patch("dict.ai.query_parse.parse_query") as mock_parse:
            page = self.client.get(
                reverse("ai_search"),
                {"job": job_id, "query": "коза", "sort": "alpha"},
            )
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, "kaza")
            self.assertContains(page, "по алфавиту")
            mock_parse.assert_not_called()

        with patch("dict.ai.query_parse.parse_query") as mock_parse:
            partial = self.client.get(
                reverse("ai_search_job_partial", args=[job_id]),
                {"sort": "alpha"},
            )
            self.assertEqual(partial.status_code, 200)
            self.assertContains(partial, "kaza")
            mock_parse.assert_not_called()

    def test_create_empty_rejected(self):
        resp = self.client.post(
            reverse("ai_search_job_create"),
            data=json.dumps({"query": "  "}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_status_404(self):
        import uuid

        resp = self.client.get(reverse("ai_search_job_status", args=[uuid.uuid4()]))
        self.assertEqual(resp.status_code, 404)
