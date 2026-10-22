from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from dict.ai.classify_bg import (
    format_classify_notice_message,
    pop_classify_notices,
    push_classify_notice,
    schedule_classify_article,
)
from dict.middleware import OntologyClassifyNoticeMiddleware
from dict.models import Article


class ClassifyNoticeHelpersTestCase(TestCase):
    def tearDown(self):
        from dict.ai import classify_bg

        with classify_bg._notices_lock:
            classify_bg._pending_notices.clear()
        with classify_bg._lock:
            classify_bg._inflight.clear()

    def test_format_ok_with_fields(self):
        text = format_classify_notice_message(
            {
                "ok": True,
                "word": "kissa",
                "fields": ["животные", "еда"],
                "no_field": False,
            }
        )
        self.assertIn("kissa", text)
        self.assertIn("животные", text)

    def test_format_ok_no_field(self):
        text = format_classify_notice_message(
            {"ok": True, "word": "ja", "fields": [], "no_field": True}
        )
        self.assertIn("no_field", text)

    def test_format_error(self):
        text = format_classify_notice_message(
            {"ok": False, "word": "x", "error": "llm_unavailable"}
        )
        self.assertIn("не удалось", text)
        self.assertIn("llm_unavailable", text)

    def test_push_pop(self):
        push_classify_notice(7, {"ok": True, "word": "a", "fields": []})
        push_classify_notice(7, {"ok": False, "word": "b", "error": "x"})
        self.assertEqual(len(pop_classify_notices(7)), 2)
        self.assertEqual(pop_classify_notices(7), [])

    def test_schedule_pushes_notice_for_user(self):
        art = Article.objects.create(word="noticeword")
        with patch("dict.ai.classify_bg.threading.Thread") as thread_cls:
            self.assertTrue(schedule_classify_article(art.pk, user_id=3))
            runner = (
                thread_cls.call_args.kwargs.get("target") or thread_cls.call_args[0][0]
            )
        with (
            patch("django.db.close_old_connections"),
            patch(
                "dict.ai.classify.classify_article",
                return_value={
                    "ok": True,
                    "fields": ["еда"],
                    "no_field": False,
                    "error": None,
                },
            ),
        ):
            runner()
        notices = pop_classify_notices(3)
        self.assertEqual(len(notices), 1)
        self.assertTrue(notices[0]["ok"])
        self.assertEqual(notices[0]["word"], "noticeword")
        self.assertEqual(notices[0]["fields"], ["еда"])


class OntologyClassifyNoticeMiddlewareTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "a@example.com", "x")
        self.factory = RequestFactory()

    def tearDown(self):
        from dict.ai import classify_bg

        with classify_bg._notices_lock:
            classify_bg._pending_notices.clear()

    def test_flushes_on_admin_get(self):
        push_classify_notice(
            self.user.pk,
            {
                "ok": True,
                "article_id": 1,
                "word": "kissa",
                "fields": ["животные"],
                "no_field": False,
            },
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("admin:dict_article_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "kissa")
        self.assertContains(response, "размечено")
        self.assertEqual(pop_classify_notices(self.user.pk), [])

    def test_skips_non_admin(self):
        push_classify_notice(
            self.user.pk,
            {"ok": True, "word": "x", "fields": ["еда"], "no_field": False},
        )
        request = self.factory.get("/")
        request.user = self.user
        middleware = OntologyClassifyNoticeMiddleware(lambda r: None)
        middleware(request)
        self.assertEqual(len(pop_classify_notices(self.user.pk)), 1)
