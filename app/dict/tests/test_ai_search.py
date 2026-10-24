from django.test import TestCase

from dict.ai.rank import SORT_ALPHA, SORT_RELEVANCE, lemmas_with_exact_translate
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
    ArticleLink,
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

    def test_dialect_only_returns_dialect_articles(self):
        """«весьегонский говор» → dialect всг., no lexical → all всг. hits."""
        groups, fallback = search_by_parsed(
            self._parsed(
                query="весьегонский говор",
                lexical=[],
                dialect="всг.",
            )
        )
        self.assertIsNone(fallback)
        self.assertEqual(len(groups), 1)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("kaza-vsg", words)
        self.assertNotIn("kaza", words)

    def test_see_referrer_demoted_on_relevance_not_alpha(self):
        """см./от pull-in sinks to bottom on relevance; alpha keeps ABC order."""
        head = Article.objects.create(word="veičči", article_html="<b>veičči</b>")
        ArticleIndexTranslate.objects.create(article=head, rus_word="нож")
        stub = Article.objects.create(word="aaa-see", article_html="<b>см.</b>")
        ArticleLink.objects.create(
            from_article=stub, to_article=head, kind=ArticleLink.KIND_SEE
        )
        other = Article.objects.create(word="mmm-lex", article_html="<b>m</b>")
        ArticleIndexTranslate.objects.create(article=other, rus_word="хлеб")

        parsed = self._parsed(
            query="чем режут хлеб",
            lexical=["хлеб"],
            focus=["нож"],
            related=[],
            fields=[],
        )
        by_rel, _ = search_by_parsed(parsed, sort=SORT_RELEVANCE)
        words_rel = [a["word"] for a in by_rel[0]["articles"]]
        self.assertIn("veičči", words_rel)
        self.assertIn("aaa-see", words_rel)
        self.assertEqual(words_rel[-1], "aaa-see")
        self.assertLess(words_rel.index("veičči"), words_rel.index("aaa-see"))

        by_alpha, _ = search_by_parsed(parsed, sort=SORT_ALPHA)
        words_alpha = [a["word"] for a in by_alpha[0]["articles"]]
        self.assertEqual(words_alpha[0], "aaa-see")  # alphabetically first

    def test_outgoing_see_target_not_pulled(self):
        """Hit that says см. X must not pull X; only referrers to the hit."""
        head = Article.objects.create(word="vägöväšti", article_html="<b>v</b>")
        ArticleIndexTranslate.objects.create(article=head, rus_word="пиво")
        ArticleIndexTranslate.objects.create(article=head, rus_word="сильно")
        target = Article.objects.create(word="vägöväh", article_html="<b>см.</b>")
        ArticleLink.objects.create(
            from_article=head, to_article=target, kind=ArticleLink.KIND_SEE
        )
        stub = Article.objects.create(word="aaa-stub", article_html="<b>см.</b>")
        ArticleLink.objects.create(
            from_article=stub, to_article=head, kind=ArticleLink.KIND_SEE
        )

        groups, _ = search_by_parsed(
            self._parsed(
                query="пиво", lexical=["пиво"], focus=[], related=[], fields=[]
            )
        )
        words = [a["word"] for a in groups[0]["articles"]]
        self.assertIn("vägöväšti", words)
        self.assertIn("aaa-stub", words)
        self.assertNotIn("vägöväh", words)

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

    def test_multiword_focus_does_not_or_partial_token(self):
        """«родственные связи» must not boost «половую связь» above kinship names."""
        kin = SemanticField.objects.create(
            name="Социум и родство", definition="родство", sorting=4
        )
        sex = Article.objects.create(word="pilluttua", article_html="<b>p</b>")
        ArticleIndexTranslate.objects.create(
            article=sex, rus_word="вступать в половую связь"
        )
        ArticleSemanticField.objects.create(article=sex, field=kin)
        grandma = Article.objects.create(word="baba", article_html="<b>baba</b>")
        ArticleIndexTranslate.objects.create(article=grandma, rus_word="бабушка")
        ArticleSemanticField.objects.create(article=grandma, field=kin)
        kin_lex = Article.objects.create(word="rodnuš", article_html="<b>r</b>")
        ArticleIndexTranslate.objects.create(article=kin_lex, rus_word="родство")
        ArticleSemanticField.objects.create(article=kin_lex, field=kin)

        groups, _ = search_by_parsed(
            self._parsed(
                query="названия родственных связей",
                lexical=["родство", "родственные связи"],
                focus=["родственные связи"],
                related=["бабушка", "дедушка"],
                fields=["Социум и родство"],
            ),
            sort=SORT_RELEVANCE,
        )
        words = [a["word"] for a in groups[0]["articles"]]
        self.assertIn("baba", words)
        self.assertIn("rodnuš", words)
        # False friend via token «связи» must not lead the list.
        if "pilluttua" in words:
            self.assertGreater(words.index("pilluttua"), words.index("baba"))
            self.assertGreater(words.index("pilluttua"), words.index("rodnuš"))
        self.assertLess(words.index("rodnuš"), words.index("baba"))

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

    def test_enrich_prefers_lexical_theme_over_related(self):
        """«про животных» in lexical must beat related «поведение» from «примета»."""
        ArticleIndexTranslate.objects.create(article=self.a_lex, rus_word="животные")
        behavior = SemanticField.objects.create(
            name="Характер и поведение", definition="характер", sorting=5
        )
        noisy = Article.objects.create(word="beh", article_html="<b>beh</b>")
        ArticleIndexTranslate.objects.create(article=noisy, rus_word="поведение")
        ArticleSemanticField.objects.create(article=noisy, field=behavior)
        enriched = _enrich_fields(
            [],
            focus=[],
            related=["поведение", "признаки"],
            lexical=["животные"],
        )
        self.assertIn("Животный мир", enriched)
        self.assertEqual(enriched[0], "Животный мир")

    def test_marks_plus_theme_uses_field_intersect_tags(self):
        """
        «глаголы в приметах про животных»: field ∩ tags, not weak lexical ∩ tags.
        Omen verbs in animals often lack the translation «животные».
        """
        tag_priem = Tag.objects.create(
            tag="примета", name="примета", type=3, sorting=20
        )
        tag_v = Tag.objects.create(
            tag="v", name="verbum, глагол", type=2, level=0, sorting=1
        )
        # Seed for enrich: «животные» on an animals-field article (not the omen verb).
        ArticleIndexTranslate.objects.create(article=self.a_lex, rus_word="животные")
        # In animals + omen verb — no «животные» translation of its own
        good = Article.objects.create(word="ulvuo", article_html="<b>ulvuo</b>")
        ArticleIndexTranslate.objects.create(article=good, rus_word="выть")
        ArticleSemanticField.objects.create(article=good, field=self.field)
        ArticleIndexTag.objects.create(article=good, tag=tag_priem)
        ArticleIndexTag.objects.create(article=good, tag=tag_v)
        # Lexical «животные» ∩ tags outside the animals field
        noise = Article.objects.create(word="noise-v", article_html="<b>n</b>")
        ArticleIndexTranslate.objects.create(article=noise, rus_word="животные")
        ArticleIndexTag.objects.create(article=noise, tag=tag_priem)
        ArticleIndexTag.objects.create(article=noise, tag=tag_v)

        groups, _ = search_by_parsed(
            self._parsed(
                query="глаголы в приметах про животных",
                lexical=["животные"],
                related=["поведение"],
                fields=[],  # enrich should add Животный мир
                tags=["примета", "v"],
            )
        )
        self.assertEqual(len(groups), 1)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("ulvuo", words)
        self.assertNotIn("noise-v", words)
        field_names = [f["name"] for f in groups[0].get("fields") or []]
        self.assertIn("Животный мир", field_names)

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

    def test_soft_tag_unions_field_pool_even_under_hard_pos(self):
        """Inferred soft mark enters via soft∩field; hard v must not hide it."""
        tag_v = Tag.objects.create(
            tag="v", name="verbum, глагол", type=2, level=0, sorting=1
        )
        # Verb in field (hard v ∩ field path) — not бран.
        verb = Article.objects.create(word="riijellä", article_html="<b>r</b>")
        ArticleIndexTranslate.objects.create(article=verb, rus_word="ругаться")
        ArticleIndexTag.objects.create(article=verb, tag=tag_v)
        ArticleSemanticField.objects.create(article=verb, field=self.field)
        # Soft-mark hit in same field, no v (like бранн. nouns in prod).
        swear = Article.objects.create(word="pahala", article_html="<b>p</b>")
        ArticleIndexTag.objects.create(article=swear, tag=self.tag_br)
        ArticleSemanticField.objects.create(article=swear, field=self.field)
        # Soft mark outside field — must not leak in.
        outside = Article.objects.create(word="out-br", article_html="<b>o</b>")
        ArticleIndexTag.objects.create(article=outside, tag=self.tag_br)

        groups, fallback = search_by_parsed(
            self._parsed(
                query="как ругаться на карельском",
                lexical=["ругаться"],
                focus=["ругаться"],
                fields=["Животный мир"],
                tags=["v"],
                tags_soft=["бран."],
            )
        )
        self.assertIsNone(fallback)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("riijellä", words)
        self.assertIn("pahala", words)
        self.assertNotIn("out-br", words)

    def test_pos_narrows_theme_not_all_field_verbs(self):
        """«глаголы … варить пиво» → theme∩v, not every verb in the food field."""
        food = SemanticField.objects.create(
            name="Пища и напитки", definition="еда", sorting=2
        )
        tag_v = Tag.objects.create(
            tag="v", name="verbum, глагол", type=2, level=0, sorting=1
        )
        cook = Article.objects.create(word="keittiä", article_html="<b>k</b>")
        ArticleIndexTranslate.objects.create(article=cook, rus_word="варить")
        ArticleIndexTag.objects.create(article=cook, tag=tag_v)
        ArticleSemanticField.objects.create(article=cook, field=food)
        # Verb in same field, unrelated lemma — must not appear via field∩v dump.
        noise = Article.objects.create(word="ajatella", article_html="<b>a</b>")
        ArticleIndexTranslate.objects.create(article=noise, rus_word="думать")
        ArticleIndexTag.objects.create(article=noise, tag=tag_v)
        ArticleSemanticField.objects.create(article=noise, field=food)

        groups, fallback = search_by_parsed(
            self._parsed(
                query="глаголы про то как варить пиво",
                lexical=["варить", "пиво"],
                fields=["Пища и напитки"],
                tags=["v"],
            )
        )
        self.assertIsNone(fallback)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("keittiä", words)
        self.assertNotIn("ajatella", words)

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

    def test_dialect_plus_field_uses_field_pool_not_all_dialect(self):
        """Theme + всг. with empty lemma∩field → field∩всг., not every всг. article."""
        weather = SemanticField.objects.create(
            name="Природа и погода", definition="погода", sorting=2
        )
        # всг. in weather field
        rain = Article.objects.create(word="vihma-vsg", article_html="<b>v</b>")
        ArticleIndexTag.objects.create(article=rain, tag=self.tag_d)
        ArticleSemanticField.objects.create(article=rain, field=weather)
        # всг. outside weather (other field only) — must not appear
        other = Article.objects.create(word="other-vsg", article_html="<b>o</b>")
        ArticleIndexTag.objects.create(article=other, tag=self.tag_d)
        ArticleIndexTranslate.objects.create(article=other, rus_word="прочее")
        # lemma «погода» misses; field still set
        groups, fallback = search_by_parsed(
            self._parsed(
                query="весьегонские слова про погоду",
                lexical=["погоданеттакогоxyz"],
                fields=["Природа и погода"],
                dialect="всг.",
            )
        )
        self.assertIsNone(fallback)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("vihma-vsg", words)
        self.assertNotIn("other-vsg", words)
        self.assertNotIn("kaza-vsg", words)
        self.assertFalse(groups[0].get("dialect_relaxed"))

    def test_dialect_empty_lemma_relaxes_to_lexical_not_enrich_neighbors(self):
        """
        Lemma∩всг. empty → relax dialect, keep lexical anchors ∩ LLM field.
        Do not pull enrich-neighbor всг. articles (Состояние…).
        """
        weather = SemanticField.objects.create(
            name="Природа и погода", definition="погода", sorting=2
        )
        state = SemanticField.objects.create(
            name="Состояние и изменение", definition="состояние", sorting=3
        )
        seed = Article.objects.create(word="seed-pogoda", article_html="<b>s</b>")
        ArticleIndexTranslate.objects.create(article=seed, rus_word="погода")
        ArticleSemanticField.objects.create(article=seed, field=weather)
        mood = Article.objects.create(word="mood-vsg", article_html="<b>m</b>")
        ArticleIndexTag.objects.create(article=mood, tag=self.tag_d)
        ArticleSemanticField.objects.create(article=mood, field=state)
        ArticleIndexTranslate.objects.create(article=mood, rus_word="погода")
        groups, fallback = search_by_parsed(
            self._parsed(
                query="весьегонские слова про погоду",
                lexical=["погода"],
                fields=["Природа и погода"],
                dialect="всг.",
            )
        )
        self.assertIsNone(fallback)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("seed-pogoda", words)
        self.assertNotIn("mood-vsg", words)
        self.assertNotIn("kaza-vsg", words)
        self.assertTrue(groups[0].get("dialect_relaxed"))
        shown = [f["name"] for f in groups[0].get("fields") or []]
        self.assertEqual(shown, ["Природа и погода"])

    def test_dialect_rich_lexical_uses_lemmas_not_whole_field(self):
        """Model anchors (дождь, снег…) → lemma hits, not dump of field∩всг."""
        weather = SemanticField.objects.create(
            name="Природа и погода", definition="погода", sorting=2
        )
        rain = Article.objects.create(word="vihma", article_html="<b>v</b>")
        ArticleIndexTranslate.objects.create(article=rain, rus_word="дождь")
        ArticleSemanticField.objects.create(article=rain, field=weather)
        # всг. landscape in same field — must not appear via field dump
        land = Article.objects.create(word="alava-vsg", article_html="<b>a</b>")
        ArticleIndexTag.objects.create(article=land, tag=self.tag_d)
        ArticleSemanticField.objects.create(article=land, field=weather)
        ArticleIndexTranslate.objects.create(article=land, rus_word="низина")
        # KW-only всг. hit must not block relax-to-lemmas
        omen = Article.objects.create(word="omen-vsg", article_html="<b>o</b>")
        ArticleIndexTag.objects.create(article=omen, tag=self.tag_d)
        ArticleSemanticField.objects.create(article=omen, field=weather)
        ArticleKeyword.objects.create(article=omen, word="дождь")
        groups, fallback = search_by_parsed(
            self._parsed(
                query="весьегонские слова про погоду",
                lexical=["погода", "дождь", "снег", "ветер"],
                fields=["Природа и погода"],
                dialect="всг.",
            )
        )
        self.assertIsNone(fallback)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("vihma", words)
        self.assertNotIn("alava-vsg", words)
        self.assertNotIn("kaza-vsg", words)
        self.assertTrue(groups[0].get("dialect_relaxed"))

    def test_dialect_plus_field_relaxes_when_field_dialect_empty(self):
        """field∩всг. empty → show theme without dialect, not all всг."""
        weather = SemanticField.objects.create(
            name="Природа и погода", definition="погода", sorting=2
        )
        # weather article WITHOUT всг.
        rain = Article.objects.create(word="vihma", article_html="<b>v</b>")
        ArticleIndexTranslate.objects.create(article=rain, rus_word="дождь")
        ArticleSemanticField.objects.create(article=rain, field=weather)
        # всг. only in another field (setUp kaza-vsg)
        groups, fallback = search_by_parsed(
            self._parsed(
                query="весьегонская погода",
                lexical=["дождь"],
                fields=["Природа и погода"],
                dialect="всг.",
            )
        )
        self.assertIsNone(fallback)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("vihma", words)
        self.assertNotIn("kaza-vsg", words)
        self.assertTrue(groups[0].get("dialect_relaxed"))

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

    def test_missed_lemmas_still_browse_named_field(self):
        """Named field + missing lemmas → browse field pool (not empty fallback)."""
        groups, fallback = search_by_parsed(
            self._parsed(
                query="коза",
                lexical=["несуществующеесловоxyz"],
                related=["тоженеттакогоabc"],
                fields=["Животный мир"],
            )
        )
        self.assertIsNone(fallback)
        words = {a["word"] for a in groups[0]["articles"]}
        self.assertIn("lehmä", words)
        self.assertIn("kaza", words)

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

        page_ok, page_detail = check_benchmark_case(
            {
                "ok": True,
                "parse_ok": True,
                "lexical": ["Животные"],
                "tags": ["примета"],
                "fields": ["Животный мир"],
                "dialect": "всг.",
            },
            {
                "lexical_any": ["животное", "животные"],
                "tags_contains": ["примета"],
                "dialect": "всг.",
                "must_not_have_tags": ["с.-х."],
            },
        )
        self.assertTrue(page_ok, page_detail)


class LemmasWithExactTranslateTestCase(TestCase):
    def test_keeps_only_lemmas_present_as_translations(self):
        art = Article.objects.create(word="olut", article_html="<b>olut</b>")
        ArticleIndexTranslate.objects.create(article=art, rus_word="пиво")
        ArticleIndexTranslate.objects.create(article=art, rus_word="хмель")
        self.assertEqual(
            lemmas_with_exact_translate(["дрожжи", "хмель", "сусло", "пиво", "хмель"]),
            ["хмель", "пиво"],
        )
