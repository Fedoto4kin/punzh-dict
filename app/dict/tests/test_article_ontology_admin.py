from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from dict.ai.classify_bg import (
    article_has_ontology_markup,
    schedule_classify_article,
)
from dict.ai.ontology_status import BUCKET_MARKED, BUCKET_PENDING, BUCKET_SKIP
from dict.models import (
    Article,
    ArticleIndexTranslate,
    ArticleKeyword,
    ArticleSemanticField,
    SemanticField,
    Source,
)


class ArticleHasOntologyMarkupTestCase(TestCase):
    def test_empty_article_is_unclassified(self):
        art = Article.objects.create(word="tyhja")
        self.assertFalse(article_has_ontology_markup(art))

    def test_field_counts_as_classified(self):
        art = Article.objects.create(word="kettu")
        field = SemanticField.objects.create(name="животные", sorting=1)
        ArticleSemanticField.objects.create(article=art, field=field)
        self.assertTrue(article_has_ontology_markup(art))

    def test_keyword_only_counts_as_classified(self):
        art = Article.objects.create(word="sm")
        ArticleKeyword.objects.create(article=art, word="см")
        self.assertTrue(article_has_ontology_markup(art))


class ScheduleClassifyArticleTestCase(TestCase):
    def tearDown(self):
        from dict.ai import classify_bg

        with classify_bg._lock:
            classify_bg._inflight.clear()

    def test_second_schedule_while_inflight_returns_false(self):
        started = []

        def fake_start(*args, **kwargs):
            started.append(True)

        with patch("dict.ai.classify_bg.threading.Thread") as thread_cls:
            thread_cls.return_value.start.side_effect = fake_start
            self.assertTrue(schedule_classify_article(42))
            self.assertFalse(schedule_classify_article(42))
            self.assertEqual(len(started), 1)
            # Release the in-flight slot by running the captured target once.
            runner = (
                thread_cls.call_args.kwargs.get("target") or thread_cls.call_args[0][0]
            )
            with (
                patch("django.db.close_old_connections"),
                patch(
                    "dict.ai.classify.classify_article",
                    return_value={"ok": True},
                ),
            ):
                runner()
            self.assertTrue(schedule_classify_article(42))


class OntologyQueueAdminTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "a@example.com", "x")
        self.client.force_login(self.user)
        self.pending = Article.objects.create(word="pending")
        ArticleIndexTranslate.objects.create(article=self.pending, rus_word="хлеб")
        self.with_field = Article.objects.create(word="kissa")
        self.with_kw = Article.objects.create(word="leipa")
        self.empty = Article.objects.create(word="seestub", article_html="<i>см.</i> x")
        self.field = SemanticField.objects.create(name="еда", sorting=1)
        ArticleSemanticField.objects.create(article=self.with_field, field=self.field)
        ArticleKeyword.objects.create(article=self.with_kw, word="хлеб")
        self.queue_url = reverse("admin:dict_ontologyqueuearticle_changelist")

    def test_queue_defaults_to_pending(self):
        response = self.client.get(self.queue_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("ontology=pending", response["Location"])

    def test_queue_filter_pending(self):
        response = self.client.get(self.queue_url, {"ontology": BUCKET_PENDING})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Поля", html)
        self.assertIn("Материал", html)
        self.assertIn("POS", html)
        self.assertIn("перевод", html)
        self.assertIn(
            f"/admin/dict/ontologyqueuearticle/{self.pending.pk}/change/", html
        )
        self.assertNotIn(
            f"/admin/dict/ontologyqueuearticle/{self.with_field.pk}/change/", html
        )
        self.assertNotIn(
            f"/admin/dict/ontologyqueuearticle/{self.with_kw.pk}/change/", html
        )
        self.assertNotIn(
            f"/admin/dict/ontologyqueuearticle/{self.empty.pk}/change/", html
        )

    def test_queue_filter_marked(self):
        response = self.client.get(self.queue_url, {"ontology": BUCKET_MARKED})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(
            f"/admin/dict/ontologyqueuearticle/{self.with_field.pk}/change/", html
        )
        self.assertNotIn(
            f"/admin/dict/ontologyqueuearticle/{self.pending.pk}/change/", html
        )
        self.assertNotIn(
            f"/admin/dict/ontologyqueuearticle/{self.with_kw.pk}/change/", html
        )

    def test_queue_filter_skip(self):
        response = self.client.get(self.queue_url, {"ontology": BUCKET_SKIP})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(
            f"/admin/dict/ontologyqueuearticle/{self.with_kw.pk}/change/", html
        )
        self.assertIn(f"/admin/dict/ontologyqueuearticle/{self.empty.pk}/change/", html)
        self.assertNotIn(
            f"/admin/dict/ontologyqueuearticle/{self.with_field.pk}/change/", html
        )
        self.assertNotIn(
            f"/admin/dict/ontologyqueuearticle/{self.pending.pk}/change/", html
        )

    def test_queue_change_redirects_to_article(self):
        response = self.client.get(
            reverse("admin:dict_ontologyqueuearticle_change", args=[self.pending.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("admin:dict_article_change", args=[self.pending.pk]),
        )

    def test_semanticfield_changelist_links_queue(self):
        response = self.client.get(reverse("admin:dict_semanticfield_changelist"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Очередь разметки", html)
        self.assertIn(self.queue_url, html)

    def test_queue_action_is_reclassify_not_delete(self):
        response = self.client.get(self.queue_url, {"ontology": BUCKET_PENDING})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Переклассифицировать", html)
        self.assertNotIn("delete_selected", html)

    def test_queue_reclassify_action_schedules(self):
        other = Article.objects.create(word="pending2")
        ArticleIndexTranslate.objects.create(article=other, rus_word="молоко")
        with patch(
            "dict.admin.schedule_classify_article", return_value=True
        ) as schedule:
            response = self.client.post(
                self.queue_url + f"?ontology={BUCKET_PENDING}",
                {
                    "action": "reclassify_selected",
                    "select_across": "0",
                    "index": "0",
                    "_selected_action": [str(self.pending.pk), str(other.pk)],
                },
            )
        self.assertEqual(response.status_code, 302)
        called_ids = sorted(c.args[0] for c in schedule.call_args_list)
        self.assertEqual(called_ids, sorted([self.pending.pk, other.pk]))
        for call in schedule.call_args_list:
            self.assertEqual(call.kwargs.get("user_id"), self.user.pk)

    def test_admin_index_shows_ontology_group_and_pending_count(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Онтология", html)
        self.assertIn("Смысловые поля", html)
        # Badge = pending count; one pending in setUp.
        self.assertRegex(html, r"Разметка\s*\(1\)")
        self.assertNotIn("Очередь онтологии", html)
        self.assertNotIn("Ждут разметки", html)


class ArticleOntologyAdminTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "a@example.com", "x")
        self.client.force_login(self.user)
        self.pending = Article.objects.create(word="pending")
        ArticleIndexTranslate.objects.create(article=self.pending, rus_word="хлеб")
        self.with_field = Article.objects.create(word="kissa")
        self.field = SemanticField.objects.create(name="еда", sorting=1)
        ArticleSemanticField.objects.create(article=self.with_field, field=self.field)

    def test_article_changelist_has_no_ontology_filter_or_column(self):
        response = self.client.get(reverse("admin:dict_article_changelist"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn("?ontology=", html)
        self.assertNotIn('id="changelist-filter"', html)
        self.assertNotIn("column-ontology", html)
        self.assertIn(f"/admin/dict/article/{self.pending.pk}/change/", html)
        self.assertIn(f"/admin/dict/article/{self.with_field.pk}/change/", html)

    def test_change_form_button_razmetit(self):
        response = self.client.get(
            reverse("admin:dict_article_change", args=[self.pending.pk])
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Разметить по онтологии", html)
        self.assertNotIn("Переразметить по онтологии", html)
        self.assertIn(
            reverse("admin:dict_article_classify", args=[self.pending.pk]),
            html,
        )

    def test_change_form_button_pererazmetit(self):
        response = self.client.get(
            reverse("admin:dict_article_change", args=[self.with_field.pk])
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Переразметить по онтологии", html)
        self.assertIn(
            "Перезаписать смысловые поля этой статьи?",
            html,
        )

    def test_classify_post_schedules(self):
        url = reverse("admin:dict_article_classify", args=[self.pending.pk])
        with patch(
            "dict.admin.schedule_classify_article", return_value=True
        ) as schedule:
            response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        schedule.assert_called_once_with(self.pending.pk, user_id=self.user.pk)

    def test_classify_get_not_allowed(self):
        url = reverse("admin:dict_article_classify", args=[self.pending.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_add_schedules_classify(self):
        import re

        source = Source.objects.create(title="test-src")
        add_html = self.client.get(reverse("admin:dict_article_add")).content.decode()
        prefixes = sorted(
            set(
                n.replace("-TOTAL_FORMS", "")
                for n in re.findall(r'name="([^"]+-TOTAL_FORMS)"', add_html)
            )
        )
        data = {
            "word": "uusisana",
            "word_normalized": "",
            "article_html": "новый",
            "source": str(source.pk),
            "source_detalization": "",
            "_save": "1",
        }
        for prefix in prefixes:
            data[f"{prefix}-TOTAL_FORMS"] = "0"
            data[f"{prefix}-INITIAL_FORMS"] = "0"
            data[f"{prefix}-MIN_NUM_FORMS"] = "0"
            data[f"{prefix}-MAX_NUM_FORMS"] = "1000"
        with patch(
            "dict.admin.schedule_classify_article", return_value=True
        ) as schedule:
            response = self.client.post(reverse("admin:dict_article_add"), data)
        self.assertEqual(response.status_code, 302)
        art = Article.objects.get(word="uusisana")
        schedule.assert_called_once_with(art.pk, user_id=self.user.pk)
