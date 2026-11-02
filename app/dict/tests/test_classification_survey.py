import json

from django.test import Client, TestCase, override_settings

from dict.classification_survey import (
    CONTENT_POS_TAGS,
    pick_task_article_ids,
    validate_and_store_answers,
)
from dict.models import (
    Article,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ClassificationSurveyResponse,
    SemanticField,
    Tag,
)


@override_settings(CLASSIFICATION_SURVEY=True)
class ClassificationSurveyTestCase(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.fields = []
        for i, name in enumerate(["Пища и напитки", "Животный мир", "Речь и звуки"]):
            self.fields.append(
                SemanticField.objects.create(
                    name=name, definition=f"def {name}", sorting=i
                )
            )
        self.pos = {}
        for tag, name in (
            ("s", "substantivum"),
            ("v", "verbum"),
            ("a", "adjectivum"),
            ("adv", "adverbium"),
        ):
            self.pos[tag] = Tag.objects.create(tag=tag, name=name, type=2, sorting=1)

        self.articles = []
        for i, (word, tag, tr) in enumerate(
            [
                ("kala", "s", "рыба"),
                ("juuva", "v", "пить"),
                ("hüvä", "a", "хороший"),
                ("terävästi", "adv", "остро"),
            ]
        ):
            art = Article.objects.create(
                word=word,
                first_letter=word[0].upper(),
                article_html=f"<b>{word}</b> <i>{tag}</i> {tr}; пример текста статьи",
            )
            ArticleIndexTranslate.objects.create(article=art, rus_word=tr)
            ArticleIndexTag.objects.create(article=art, tag=self.pos[tag])
            self.articles.append(art)

        # Empty body — must not be eligible.
        empty = Article.objects.create(
            word="tyhja", first_letter="T", article_html="   "
        )
        ArticleIndexTranslate.objects.create(article=empty, rus_word="пустой")
        ArticleIndexTag.objects.create(article=empty, tag=self.pos["s"])

        # No translation — ineligible.
        no_tr = Article.objects.create(
            word="ei",
            first_letter="E",
            article_html="<b>ei</b> без перевода но тело есть достаточно",
        )
        ArticleIndexTag.objects.create(article=no_tr, tag=self.pos["s"])

    def test_status_enabled(self):
        r = self.client.get("/research/classification-survey/status/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["enabled"])

    @override_settings(CLASSIFICATION_SURVEY=False)
    def test_status_disabled(self):
        r = self.client.get("/research/classification-survey/status/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["enabled"])

    def test_task_returns_three_with_pos_diversity(self):
        r = self.client.get(
            "/research/classification-survey/task/", {"key": "test-key-01"}
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data["articles"]), 3)
        self.assertGreaterEqual(len(data["fields"]), 3)
        for art in data["articles"]:
            self.assertTrue(art["translations"])
            self.assertTrue(art["url"].startswith("/search/"))
            self.assertTrue(set(art["pos"]) & set(CONTENT_POS_TAGS))
        words = {a["word"] for a in data["articles"]}
        self.assertNotIn("tyhja", words)
        self.assertNotIn("ei", words)

    def test_submit_stores_answers(self):
        task = self.client.get(
            "/research/classification-survey/task/", {"key": "test-key-02"}
        ).json()
        answers = []
        for i, art in enumerate(task["articles"]):
            if i == 0:
                answers.append(
                    {
                        "article_id": art["article_id"],
                        "decision": "fields",
                        "fields": ["Пища и напитки"],
                    }
                )
            else:
                answers.append(
                    {
                        "article_id": art["article_id"],
                        "decision": "no_field",
                        "fields": [],
                    }
                )
        self.client.get("/")
        csrf = self.client.cookies.get("csrftoken")
        self.assertIsNotNone(csrf)
        r = self.client.post(
            "/research/classification-survey/submit/",
            data=json.dumps({"key": "test-key-02", "answers": answers}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf.value,
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["stored"], 3)
        self.assertEqual(
            ClassificationSurveyResponse.objects.filter(
                respondent_key="test-key-02"
            ).count(),
            3,
        )

    def test_pick_excludes_answered(self):
        aid = self.articles[0].id
        validate_and_store_answers(
            "rep-a",
            [{"article_id": aid, "decision": "no_field", "fields": []}],
        )
        ids = pick_task_article_ids("rep-a", n=3)
        self.assertNotIn(aid, ids)

    def test_submit_one_answer_at_a_time(self):
        """Step-by-step UI saves each card immediately."""
        self.client.get("/")
        csrf = self.client.cookies["csrftoken"].value
        a1, a2 = self.articles[0], self.articles[1]
        for art, decision, fields in (
            (a1, "fields", ["Пища и напитки"]),
            (a2, "insufficient", []),
        ):
            r = self.client.post(
                "/research/classification-survey/submit/",
                data=json.dumps(
                    {
                        "key": "step-key-01",
                        "answers": [
                            {
                                "article_id": art.id,
                                "decision": decision,
                                "fields": fields,
                            }
                        ],
                    }
                ),
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf,
            )
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(r.json()["stored"], 1)
        self.assertEqual(
            ClassificationSurveyResponse.objects.filter(
                respondent_key="step-key-01"
            ).count(),
            2,
        )
