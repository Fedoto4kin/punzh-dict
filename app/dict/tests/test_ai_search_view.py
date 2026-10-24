import json
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dict.models import (
    AiSearchFeedback,
    AiSearchJob,
    AiSearchLog,
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
            "axes_display": "коза; темы: Животный мир",
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
        theme_href = reverse("ontology_field", args=[self.field.id])
        self.assertContains(partial, f'href="{theme_href}"')
        self.assertContains(partial, "Животный мир")
        self.assertNotContains(partial, "Открыть тему")

        page = self.client.get(reverse("ai_search"), {"job": job_id})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "искали: коза")
        self.assertContains(page, "kaza")
        self.assertContains(page, f'href="{theme_href}"')
        self.assertNotContains(page, "Открыть тему")

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

    def test_job_isolated_to_creating_session(self):
        """Another session must not poll / partial / ?job= for this UUID."""
        from django.test import Client

        from dict.ai.jobs import run_job

        mock_parsed = self._parsed_ok()
        with patch("dict.ai.jobs.schedule_ai_search_job", return_value=True):
            resp = self.client.post(
                reverse("ai_search_job_create"),
                data=json.dumps({"query": "коза", "sort": "relevance"}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 202)
        job_id = resp.json()["id"]
        job = AiSearchJob.objects.get(pk=job_id)
        self.assertTrue(job.client_key)

        with patch("dict.ai.query_parse.parse_query", return_value=mock_parsed):
            run_job(job_id)

        # Owner session still OK.
        self.assertEqual(
            self.client.get(reverse("ai_search_job_status", args=[job_id])).status_code,
            200,
        )

        other = Client()
        st = other.get(reverse("ai_search_job_status", args=[job_id]))
        self.assertEqual(st.status_code, 404)
        partial = other.get(reverse("ai_search_job_partial", args=[job_id]))
        self.assertEqual(partial.status_code, 404)
        page = other.get(reverse("ai_search"), {"job": job_id})
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context["job_missing"])
        self.assertNotContains(page, "искали: коза")


@override_settings(AI_SEARCH_LOG_QUERIES=True, AI_SEARCH_FEEDBACK=True)
class AiSearchLogFeedbackTestCase(TestCase):
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
            "axes_display": "коза; темы: Животный мир",
            "krl_headword": False,
            "warnings": [],
            "error": None,
            "meta": {
                "model": "test-model",
                "prompt_version": "1.15",
                "latency_ms": 12,
            },
        }

    def _run_job(self):
        from dict.ai.jobs import run_job

        with patch("dict.ai.jobs.schedule_ai_search_job", return_value=True):
            resp = self.client.post(
                reverse("ai_search_job_create"),
                data=json.dumps({"query": "коза", "sort": "relevance"}),
                content_type="application/json",
            )
        job_id = resp.json()["id"]
        with patch("dict.ai.query_parse.parse_query", return_value=self._parsed_ok()):
            run_job(job_id)
        return job_id

    def test_log_written_on_done(self):
        job_id = self._run_job()
        log = AiSearchLog.objects.get(job_id=job_id)
        self.assertEqual(log.query_raw, "коза")
        self.assertTrue(log.parse_ok)
        self.assertEqual(log.prompt_version, "1.15")
        self.assertTrue(log.session_key)
        self.assertTrue(log.groups_json)

    def test_log_written_on_error(self):
        from dict.ai.jobs import run_job

        with patch("dict.ai.jobs.schedule_ai_search_job", return_value=True):
            resp = self.client.post(
                reverse("ai_search_job_create"),
                data=json.dumps({"query": "коза"}),
                content_type="application/json",
            )
        job_id = resp.json()["id"]
        with patch("dict.ai.query_parse.parse_query", side_effect=RuntimeError("boom")):
            run_job(job_id)
        log = AiSearchLog.objects.get(job_id=job_id)
        self.assertFalse(log.parse_ok)
        self.assertIn("boom", log.error)

    def test_partial_includes_feedback_widget(self):
        job_id = self._run_job()
        partial = self.client.get(reverse("ai_search_job_partial", args=[job_id]))
        self.assertEqual(partial.status_code, 200)
        self.assertContains(partial, 'id="ai-feedback"')
        self.assertContains(partial, "Помогло?")

    def test_no_feedback_when_parse_unavailable(self):
        from dict.ai.jobs import run_job

        broken = {
            "ok": False,
            "parse_ok": False,
            "query": "коза",
            "lexical": [],
            "focus": [],
            "related": [],
            "fields": [],
            "tags": [],
            "place": None,
            "dialect": None,
            "dropped": [],
            "display": "",
            "axes_display": "",
            "krl_headword": False,
            "warnings": [],
            "error": "gateway_down",
        }
        with patch("dict.ai.jobs.schedule_ai_search_job", return_value=True):
            resp = self.client.post(
                reverse("ai_search_job_create"),
                data=json.dumps({"query": "коза"}),
                content_type="application/json",
            )
        job_id = resp.json()["id"]
        with patch("dict.ai.query_parse.parse_query", return_value=broken):
            run_job(job_id)
        partial = self.client.get(reverse("ai_search_job_partial", args=[job_id]))
        self.assertEqual(partial.status_code, 200)
        self.assertContains(partial, "Разбор по смыслу недоступен")
        self.assertNotContains(partial, 'id="ai-feedback"')

    def test_feedback_up_and_down(self):
        job_id = self._run_job()
        log = AiSearchLog.objects.get(job_id=job_id)

        up = self.client.post(
            reverse("ai_search_feedback"),
            data=json.dumps({"log_id": str(log.id), "vote": "up"}),
            content_type="application/json",
        )
        self.assertEqual(up.status_code, 200)
        fb = AiSearchFeedback.objects.get(log=log)
        self.assertEqual(fb.vote, "up")
        self.assertEqual(fb.reasons, [])

        down = self.client.post(
            reverse("ai_search_feedback"),
            data=json.dumps(
                {
                    "log_id": str(log.id),
                    "vote": "down",
                    "reasons": ["parse_wrong", "nope"],
                    "comment": "кривой разбор",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(down.status_code, 200)
        fb.refresh_from_db()
        self.assertEqual(fb.vote, "down")
        self.assertEqual(fb.reasons, ["parse_wrong"])
        self.assertEqual(fb.comment, "кривой разбор")

        partial = self.client.get(reverse("ai_search_job_partial", args=[job_id]))
        self.assertNotContains(partial, 'id="ai-feedback"')

    def test_feedback_other_session_rejected(self):
        job_id = self._run_job()
        log = AiSearchLog.objects.get(job_id=job_id)
        other = Client()
        resp = other.post(
            reverse("ai_search_feedback"),
            data=json.dumps({"log_id": str(log.id), "vote": "up"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(AiSearchFeedback.objects.filter(log=log).exists())
