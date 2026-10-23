from unittest.mock import patch

from django.test import TestCase, override_settings

from dict.ai.rank import SORT_ALPHA, SORT_RELEVANCE
from dict.ai.rerank import (
    apply_rerank_to_groups,
    complete_head_order,
    llm_reorder_ids,
    parse_keep_tail,
    validate_order,
    validate_permutation,
)
from dict.ai.search import search_by_parsed
from dict.models import (
    Article,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleSemanticField,
    SemanticField,
    Tag,
)


class ValidateOrderTestCase(TestCase):
    def test_full_permutation(self):
        self.assertEqual(validate_permutation([1, 2, 3], [3, 1, 2]), [3, 1, 2])

    def test_rejects_extra_or_dupes(self):
        self.assertIsNone(validate_order([1, 2], [1, 2, 3], allow_drop=False))
        self.assertIsNone(validate_order([1, 2], [1, 1], allow_drop=False))
        self.assertIsNone(validate_order([1, 2], [1, 9], allow_drop=False))

    def test_strict_permutation_rejects_subset(self):
        self.assertIsNone(validate_permutation([1, 2, 3], [1, 2]))

    def test_complete_head_order_prefix(self):
        self.assertEqual(complete_head_order([1, 2, 3, 4], [3, 1]), [3, 1, 2, 4])
        self.assertIsNone(complete_head_order([1, 2], [1, 9]))

    def test_parse_keep_tail(self):
        self.assertTrue(parse_keep_tail(True))
        self.assertFalse(parse_keep_tail(False))
        self.assertTrue(parse_keep_tail(None, default=True))
        self.assertFalse(parse_keep_tail("false"))
        self.assertTrue(parse_keep_tail("да"))


@override_settings(AI_SEARCH_LLM_RERANK=True, TIMEWEB_AI_MODEL_RERANK="test/model")
class ApplyRerankTestCase(TestCase):
    def setUp(self):
        self.field = SemanticField.objects.create(
            name="Социум и родство", definition="родство", sorting=1
        )
        self.a_kin = Article.objects.create(word="rodnuš", article_html="<b>r</b>")
        ArticleIndexTranslate.objects.create(article=self.a_kin, rus_word="родство")
        ArticleIndexTranslate.objects.create(article=self.a_kin, rus_word="связь")
        ArticleSemanticField.objects.create(article=self.a_kin, field=self.field)

        self.a_sex = Article.objects.create(word="pilluttua", article_html="<b>p</b>")
        ArticleIndexTranslate.objects.create(
            article=self.a_sex, rus_word="вступать в половую связь"
        )
        ArticleSemanticField.objects.create(article=self.a_sex, field=self.field)

        self.a_grandma = Article.objects.create(word="baba", article_html="<b>b</b>")
        ArticleIndexTranslate.objects.create(article=self.a_grandma, rus_word="бабушка")
        ArticleSemanticField.objects.create(article=self.a_grandma, field=self.field)

    def _groups(self):
        return [
            {
                "kind": "lexical",
                "title": "Нашлось",
                "total": 3,
                "more": 0,
                "articles": [
                    {"id": self.a_sex.id, "word": self.a_sex.word},
                    {"id": self.a_grandma.id, "word": self.a_grandma.word},
                    {"id": self.a_kin.id, "word": self.a_kin.word},
                ],
                "demote_ids": [],
            }
        ]

    @patch("dict.ai.rerank.ai_client.chat_json")
    def test_llm_permutation_applied(self, mock_chat):
        mock_chat.return_value = {
            "order": [self.a_kin.id, self.a_grandma.id, self.a_sex.id],
            "keep_tail": True,
        }
        groups = apply_rerank_to_groups(
            "названия родственных связей", self._groups(), sort=SORT_RELEVANCE
        )
        words = [a["word"] for a in groups[0]["articles"]]
        self.assertEqual(words, [self.a_kin.word, self.a_grandma.word, self.a_sex.word])
        user = mock_chat.call_args[0][1]
        self.assertIn("родство", user)
        self.assertIn("связь", user)
        self.assertIn("keep_tail", user)

    @patch("dict.ai.rerank.ai_client.chat_json")
    def test_invalid_order_keeps_sql(self, mock_chat):
        mock_chat.return_value = {"order": [999999], "keep_tail": False}
        groups = apply_rerank_to_groups("q", self._groups(), sort=SORT_RELEVANCE)
        words = [a["word"] for a in groups[0]["articles"]]
        self.assertEqual(words, [self.a_sex.word, self.a_grandma.word, self.a_kin.word])

    @patch("dict.ai.rerank.ai_client.chat_json")
    def test_prefix_order_completes_head(self, mock_chat):
        mock_chat.return_value = {"order": [self.a_kin.id], "keep_tail": True}
        groups = apply_rerank_to_groups("q", self._groups(), sort=SORT_RELEVANCE)
        words = [a["word"] for a in groups[0]["articles"]]
        self.assertEqual(words[0], self.a_kin.word)
        self.assertEqual(
            set(words), {self.a_sex.word, self.a_grandma.word, self.a_kin.word}
        )

    @patch("dict.ai.rerank.ai_client.chat_json")
    def test_keep_tail_false_drops_tail_only(self, mock_chat):
        extras = []
        for i in range(5):
            a = Article.objects.create(word=f"extra{i}", article_html=f"<b>e{i}</b>")
            ArticleIndexTranslate.objects.create(article=a, rus_word=f"лишнее{i}")
            extras.append(a)
        # Force head=3 by patching TOP_N via articles length: use 3 head + mark
        # extras as tail by temporarily lowering — put 3 then 5; RERANK_TOP_N=30
        # so all 8 are head. Build 32 articles so extras sit in tail.
        filler = []
        for i in range(27):
            a = Article.objects.create(word=f"fill{i}", article_html=f"<b>f{i}</b>")
            ArticleIndexTranslate.objects.create(article=a, rus_word=f"заполнитель{i}")
            filler.append(a)
        arts = [
            {"id": self.a_sex.id, "word": self.a_sex.word},
            {"id": self.a_grandma.id, "word": self.a_grandma.word},
            {"id": self.a_kin.id, "word": self.a_kin.word},
        ]
        arts += [{"id": a.id, "word": a.word} for a in filler]
        arts += [{"id": a.id, "word": a.word} for a in extras]
        groups = [
            {
                "kind": "lexical",
                "title": "Нашлось",
                "total": len(arts),
                "more": 0,
                "articles": arts,
                "demote_ids": [],
            }
        ]
        head_ids = [a["id"] for a in arts[:30]]
        order = [self.a_kin.id] + [i for i in head_ids if i != self.a_kin.id]
        self.assertEqual(len(order), 30)
        mock_chat.return_value = {"order": order, "keep_tail": False}
        out = apply_rerank_to_groups("родство", groups, sort=SORT_RELEVANCE)
        words = [a["word"] for a in out[0]["articles"]]
        self.assertEqual(words[0], self.a_kin.word)
        self.assertEqual(len(words), 30)
        self.assertTrue(out[0].get("tail_dropped"))
        for a in extras:
            self.assertNotIn(a.word, words)

    @patch("dict.ai.rerank.ai_client.chat_json")
    def test_alpha_skips_llm(self, mock_chat):
        apply_rerank_to_groups("q", self._groups(), sort=SORT_ALPHA)
        mock_chat.assert_not_called()

    @override_settings(AI_SEARCH_LLM_RERANK=False)
    @patch("dict.ai.rerank.ai_client.chat_json")
    def test_flag_off_skips_llm(self, mock_chat):
        apply_rerank_to_groups("q", self._groups(), sort=SORT_RELEVANCE)
        mock_chat.assert_not_called()

    @patch("dict.ai.rerank.ai_client.chat_json")
    def test_demote_after_permutation(self, mock_chat):
        stub = Article.objects.create(word="aaa-see", article_html="<b>см.</b>")
        groups = self._groups()
        groups[0]["articles"].append({"id": stub.id, "word": stub.word})
        groups[0]["demote_ids"] = [stub.id]
        mock_chat.return_value = {
            "order": [
                stub.id,
                self.a_kin.id,
                self.a_grandma.id,
                self.a_sex.id,
            ],
            "keep_tail": True,
        }
        out = apply_rerank_to_groups("q", groups, sort=SORT_RELEVANCE)
        words = [a["word"] for a in out[0]["articles"]]
        self.assertEqual(words[-1], stub.word)
        self.assertEqual(words[0], self.a_kin.word)


@override_settings(AI_SEARCH_LLM_RERANK=True, TIMEWEB_AI_MODEL_RERANK="test/model")
class LlmReorderIdsTestCase(TestCase):
    @patch("dict.ai.rerank.ai_client.chat_json")
    def test_returns_none_on_empty_response(self, mock_chat):
        mock_chat.return_value = None
        self.assertIsNone(
            llm_reorder_ids("q", [{"id": 1, "word": "a", "translations": []}])
        )


class SoftTagAndRelaxTestCase(TestCase):
    def test_soft_tag_does_not_and_filter_beer(self):
        Tag.objects.create(tag="с.-х.", name="сельское хозяйство", type=3, sorting=1)
        field = SemanticField.objects.create(
            name="Пища и напитки", definition="еда", sorting=1
        )
        beer = Article.objects.create(word="olut", article_html="<b>olut</b>")
        ArticleIndexTranslate.objects.create(article=beer, rus_word="пиво")
        ArticleSemanticField.objects.create(article=beer, field=field)
        farm = Article.objects.create(word="beika", article_html="<b>beika</b>")
        ArticleIndexTranslate.objects.create(article=farm, rus_word="борона")
        ArticleIndexTag.objects.create(article=farm, tag=Tag.objects.get(tag="с.-х."))

        groups, fb = search_by_parsed(
            {
                "ok": True,
                "parse_ok": True,
                "query": "как варили пиво",
                "lexical": ["варить", "пиво"],
                "focus": [],
                "related": [],
                "fields": ["Пища и напитки"],
                "tags": [],
                "tags_soft": ["с.-х."],
                "place": None,
                "dialect": None,
            }
        )
        self.assertIsNone(fb)
        words = [a["word"] for a in groups[0]["articles"]]
        self.assertIn("olut", words)
        # Soft mark must not require ∩ — beer stays without с.-х.
        # farm is с.-х. but not in food field → soft∩field must not pull it.
        self.assertNotIn("beika", words)

    def test_relax_hard_tag_when_intersection_empty(self):
        tag = Tag.objects.create(
            tag="с.-х.", name="сельское хозяйство", type=3, sorting=1
        )
        beer = Article.objects.create(word="olut2", article_html="<b>olut2</b>")
        ArticleIndexTranslate.objects.create(article=beer, rus_word="пиво")
        # Some с.-х. article exists so hard_tag_ids is non-empty, but not on beer.
        other = Article.objects.create(word="beika2", article_html="<b>b</b>")
        ArticleIndexTag.objects.create(article=other, tag=tag)
        groups, fb = search_by_parsed(
            {
                "ok": True,
                "parse_ok": True,
                "query": "пиво",
                "lexical": ["пиво"],
                "focus": [],
                "related": [],
                "fields": [],
                "tags": ["с.-х."],  # hard but ∩ lexical empty → relax
                "tags_soft": [],
                "place": None,
                "dialect": None,
            }
        )
        self.assertIsNone(fb)
        words = [a["word"] for a in groups[0]["articles"]]
        self.assertIn("olut2", words)
        self.assertNotIn("beika2", words)
        self.assertEqual(groups[0].get("tags"), None)


@override_settings(AI_SEARCH_LLM_RERANK=False)
class SearchDoesNotRequireRerankTestCase(TestCase):
    def test_search_by_parsed_still_works(self):
        a = Article.objects.create(word="kaza", article_html="<b>kaza</b>")
        ArticleIndexTranslate.objects.create(article=a, rus_word="коза")
        groups, fb = search_by_parsed(
            {
                "ok": True,
                "parse_ok": True,
                "query": "коза",
                "lexical": ["коза"],
                "focus": [],
                "related": [],
                "fields": [],
                "tags": [],
                "place": None,
                "dialect": None,
            }
        )
        self.assertIsNone(fb)
        self.assertEqual(groups[0]["articles"][0]["word"], "kaza")
        self.assertIn("demote_ids", groups[0])
