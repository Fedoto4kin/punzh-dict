from django.test import TestCase

from dict.ai.rank import SORT_ALPHA, SORT_RELEVANCE
from dict.ai.search import (
    TITLE_MAIN,
    _enrich_fields,
    check_benchmark_case,
    hydrate_group_articles,
    search_by_parsed,
)
from dict.models import (
    Article,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleKeyword,
    ArticleSemanticField,
    SemanticField,
    Tag,
)


class SearchByParsedTestCase(TestCase):
    def setUp(self):
        self.field = SemanticField.objects.create(
            name="Животный мир", definition="животные", sorting=1
        )
        self.tag_br = Tag.objects.create(tag="бран.", name="бранное", type=3, sorting=1)
        self.tag_d = Tag.objects.create(
            tag="всг.", name="весьегонский", type=4, sorting=1
        )

        self.a_lex = Article.objects.create(word="kaza", article_html="<b>kaza</b>")
        ArticleIndexTranslate.objects.create(article=self.a_lex, rus_word="коза")
        ArticleSemanticField.objects.create(article=self.a_lex, field=self.field)

        self.a_tag = Article.objects.create(word="kirota", article_html="<b>kirota</b>")
        ArticleIndexTranslate.objects.create(article=self.a_tag, rus_word="ругаться")
        ArticleIndexTag.objects.create(article=self.a_tag, tag=self.tag_br)

        self.a_field = Article.objects.create(word="lehmä", article_html="<b>lehmä</b>")
        ArticleIndexTranslate.objects.create(article=self.a_field, rus_word="корова")
        ArticleSemanticField.objects.create(article=self.a_field, field=self.field)

        self.a_dialect = Article.objects.create(
            word="kaza-vsg", article_html="<b>kaza-vsg</b>"
        )
        ArticleIndexTranslate.objects.create(article=self.a_dialect, rus_word="коза")
        ArticleIndexTag.objects.create(article=self.a_dialect, tag=self.tag_d)
        ArticleSemanticField.objects.create(article=self.a_dialect, field=self.field)

    def _parsed(self, **kwargs):
        base = {
            "ok": True,
            "parse_ok": True,
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
        }
        base.update(kwargs)
        return base

    def test_lexical_group(self):
        groups, fallback = search_by_parsed(
            self._parsed(lexical=["коза"], query="коза")
        )
        self.assertIsNone(fallback)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["kind"], "lexical")
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("kaza", words)
        self.assertGreaterEqual(groups[0]["total"], 1)

    def test_main_group_title_is_neutral(self):
        groups, _ = search_by_parsed(self._parsed(lexical=["коза"], query="коза"))
        self.assertEqual(groups[0]["title"], TITLE_MAIN)

    def test_illustration_keyword_does_not_outrank_translation(self):
        """Keyword «девочка» in a boy-article illustration must lose to real girl."""
        girl = Article.objects.create(word="tyttö", article_html="<b>tyttö</b>")
        ArticleIndexTranslate.objects.create(article=girl, rus_word="девочка")
        boy = Article.objects.create(word="uroš", article_html="<b>uroš</b> мальчик")
        ArticleIndexTranslate.objects.create(article=boy, rus_word="мальчик")
        ArticleKeyword.objects.create(article=boy, word="девочка")
        kin = SemanticField.objects.create(
            name="Социум и родство", definition="родство", sorting=4
        )
        ArticleSemanticField.objects.create(article=girl, field=kin)
        ArticleSemanticField.objects.create(article=boy, field=kin)

        groups, _ = search_by_parsed(
            self._parsed(
                query="любимая девочка",
                lexical=["девочка"],
                focus=["девочка"],
                related=[],
                fields=["Социум и родство"],
            )
        )
        words = [a["word"] for a in groups[0]["articles"]]
        self.assertIn("uroš", words)  # second-pass illustration still found
        self.assertLess(words.index("tyttö"), words.index("uroš"))

    def test_enrich_fields_adds_theme_fields(self):
        """Related/focus hits pull extra ontology fields beyond LLM's one."""
        body = SemanticField.objects.create(
            name="Человек и тело", definition="тело", sorting=3
        )
        sick = Article.objects.create(word="läzikkö", article_html="<b>läzikkö</b>")
        ArticleIndexTranslate.objects.create(article=sick, rus_word="болезнь")
        ArticleSemanticField.objects.create(article=sick, field=body)
        # LLM returned only animals; enrichment should add body via «болезнь»
        enriched = _enrich_fields(
            ["Животный мир"],
            focus=["кошка"],
            related=["болезнь", "лечение"],
            lexical=["кошка"],
        )
        self.assertIn("Животный мир", enriched)
        self.assertIn("Человек и тело", enriched)

    def test_focus_exact_ranks_first(self):
        """«чем режут хлеб» → focus нож ahead of хлеб/резать hits."""
        knife = Article.objects.create(word="veičči", article_html="<b>veičči</b>")
        ArticleIndexTranslate.objects.create(article=knife, rus_word="нож")
        bread = Article.objects.create(word="leibü", article_html="<b>leibü</b>")
        ArticleIndexTranslate.objects.create(article=bread, rus_word="хлеб")
        cut = Article.objects.create(word="leikata", article_html="<b>leikata</b>")
        ArticleIndexTranslate.objects.create(article=cut, rus_word="резать")
        field = SemanticField.objects.create(
            name="Домашняя утварь и инструменты", definition="утварь", sorting=2
        )
        for a in (knife, bread, cut):
            ArticleSemanticField.objects.create(article=a, field=field)

        groups, _ = search_by_parsed(
            self._parsed(
                query="чем режут хлеб",
                lexical=["хлеб", "резать"],
                focus=["нож"],
                related=["крошить", "ломоть"],
                fields=["Домашняя утварь и инструменты"],
            ),
            sort=SORT_RELEVANCE,
        )
        self.assertEqual(len(groups), 1)
        words = [a["word"] for a in groups[0]["articles"]]
        self.assertEqual(words[0], "veičči")
        self.assertIn("leibü", words)
        self.assertIn("leikata", words)

        alpha, _ = search_by_parsed(
            self._parsed(
                query="чем режут хлеб",
                lexical=["хлеб", "резать"],
                focus=["нож"],
                fields=["Домашняя утварь и инструменты"],
            ),
            sort=SORT_ALPHA,
        )
        alpha_words = [a["word"] for a in alpha[0]["articles"]]
        self.assertEqual(sorted(alpha_words), sorted(words))
        # alpha order differs from relevance when focus wins
        self.assertNotEqual(alpha_words[0], words[0])

    def test_krl_headword_group_not_hand_field(self):
        """Latin kazi → headword articles; ä not folded (≠ käzi/рука)."""
        cat = Article.objects.create(
            word="kaz’i, ~n’e", article_html="<b>kaz’i</b> кошка"
        )
        hand = Article.objects.create(word="käz’i", article_html="<b>käz’i</b> рука")
        groups, fallback = search_by_parsed(
            self._parsed(
                query="kazi",
                krl_headword=True,
                parse_ok=True,
                lexical=[],
                related=[],
                fields=[],
            )
        )
        self.assertIsNone(fallback)
        self.assertEqual(len(groups), 1)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn(cat.word, words)
        self.assertNotIn(hand.word, words)

    def test_tag_filters_main_with_and(self):
        """Tags AND onto main: бран. keeps kirota, drops field-only lehmä."""
        groups, fallback = search_by_parsed(
            self._parsed(
                query="ругаться",
                lexical=["ругаться"],
                related=["корова"],
                tags=["бран."],
                fields=["Животный мир"],
            )
        )
        self.assertIsNone(fallback)
        self.assertEqual(len(groups), 1)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("kirota", words)
        self.assertNotIn("lehmä", words)

    def test_priemeta_and_verb_tags(self):
        """«глаголы в приметах» → примета ∩ v."""
        tag_prim = Tag.objects.create(tag="примета", name="примета", type=3, sorting=20)
        tag_v = Tag.objects.create(
            tag="v", name="verbum, глагол", type=2, level=0, sorting=1
        )
        tag_s = Tag.objects.create(
            tag="s", name="substantivum", type=2, level=0, sorting=2
        )
        omen_v = Article.objects.create(word="ennustaa", article_html="<b>ennustaa</b>")
        ArticleIndexTag.objects.create(article=omen_v, tag=tag_prim)
        ArticleIndexTag.objects.create(article=omen_v, tag=tag_v)
        noun = Article.objects.create(word="merkki", article_html="<b>merkki</b>")
        ArticleIndexTag.objects.create(article=noun, tag=tag_prim)
        ArticleIndexTag.objects.create(article=noun, tag=tag_s)

        groups, _ = search_by_parsed(
            self._parsed(
                query="глаголы в приметах",
                lexical=[],
                focus=[],
                related=[],
                tags=["примета", "v"],
                fields=[],
            )
        )
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertEqual(words, {"ennustaa"})

    def test_lexical_and_field_merged(self):
        """Lexical + theme-in-field → one list (both on-query relevant)."""
        a_milk = Article.objects.create(word="lypsia", article_html="<b>lypsia</b>")
        ArticleIndexTranslate.objects.create(article=a_milk, rus_word="доить")
        ArticleSemanticField.objects.create(article=a_milk, field=self.field)
        ArticleKeyword.objects.create(article=a_milk, word="дойка")

        groups, _ = search_by_parsed(
            self._parsed(
                query="разведение коз",
                lexical=["коза", "разведение"],
                related=["доить", "дойка", "козёл"],
                fields=["Животный мир"],
            )
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["kind"], "lexical")
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("kaza", words)
        self.assertIn("lypsia", words)
        # unrelated field member (корова) not in related → out
        self.assertNotIn("lehmä", words)
        self.assertTrue(groups[0].get("fields"))

    def test_dialect_filters(self):
        groups, _ = search_by_parsed(
            self._parsed(lexical=["коза"], dialect="всг.", query="коза весьегонск")
        )
        self.assertEqual(len(groups), 1)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertEqual(words, {"kaza-vsg"})

    def test_fallback_when_parse_fails(self):
        groups, fallback = search_by_parsed(
            {
                "ok": False,
                "parse_ok": False,
                "query": "коза",
                "lexical": [],
                "related": [],
                "fields": [],
                "tags": [],
                "dialect": None,
            }
        )
        self.assertEqual(groups, [])
        self.assertGreaterEqual(fallback, 1)

    def test_fallback_when_related_misses_field(self):
        groups, fallback = search_by_parsed(
            self._parsed(
                query="коза",
                lexical=["несуществующеесловоxyz"],
                related=["тоженеттакогоabc"],
                fields=["Животный мир"],
            )
        )
        self.assertEqual(groups, [])
        self.assertGreaterEqual(fallback, 0)

    def test_hydrate_shows_all_cards(self):
        """Debug beta: no «ещё N» — all articles in article_objs."""
        for i in range(15):
            a = Article.objects.create(word=f"anim{i}", article_html=f"<b>anim{i}</b>")
            ArticleIndexTranslate.objects.create(article=a, rus_word="скот")
            ArticleSemanticField.objects.create(article=a, field=self.field)

        groups, _ = search_by_parsed(
            self._parsed(
                query="коза",
                lexical=["коза"],
                related=["скот"],
                fields=["Животный мир"],
            )
        )
        self.assertEqual(len(groups), 1)
        self.assertGreaterEqual(groups[0]["total"], 15)
        self.assertEqual(groups[0]["more"], 0)
        hydrated = hydrate_group_articles(groups)
        self.assertEqual(len(hydrated[0]["article_objs"]), hydrated[0]["total"])
        self.assertEqual(hydrated[0]["article_objs_more"], [])


class BenchmarkCheckTestCase(TestCase):
    def test_soft_checks(self):
        parsed = {
            "ok": True,
            "parse_ok": True,
            "lexical": ["коза", "разведение"],
            "tags": ["бран."],
            "fields": ["Животный мир"],
            "dropped": ["найди", "связанные с"],
        }
        ok, detail = check_benchmark_case(
            parsed,
            {
                "lexical_contains": ["коза"],
                "tags_any": ["бран.", "груб."],
                "dropped_contains": ["найди"],  # substring ok vs «найди все…»
                "fields_any": ["Животный мир"],
                "must_not_have_tags": ["xyz."],
            },
        )
        self.assertTrue(ok, detail)

        ok2, _ = check_benchmark_case(
            {"lexical": [], "tags": [], "fields": [], "dropped": ["найди все слова"]},
            {"dropped_contains": ["найди"]},
        )
        self.assertTrue(ok2)

        bad, _ = check_benchmark_case(
            parsed, {"lexical_contains": ["слон"], "tags_any": ["xyz."]}
        )
        self.assertFalse(bad)
