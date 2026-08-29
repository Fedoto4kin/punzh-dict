from django.test import SimpleTestCase, TestCase

from translation_cleanup import (
    SYSTEM_PROMPT_CLEAN_TRANSLATIONS,
    _drop_subsumed_auxiliaries,
    _strip_grammar_parens,
    build_cleanup_input,
    diff_translations,
    gloss_senses_from_html,
    is_service_word_article,
    parse_cleanup_json,
    pos_tags_for,
    sanitize_cleaned_translations,
)
from dict.models import Article, ArticleAddition, ArticleIndexTag, ArticleIndexTranslate, Tag

MAI_HTML = (
    "<b>mai||jata</b> <i>v</i> <ol>"
    "<li>отдавать чем-л. <i>(по вкусу)</i>; voi ~guaw tummehella масло отдает</li>"
    "<li>напоминать что-л., быть схожим; смахивать на что-л. видом; "
    "t'ämä kukka ~guaw uz'n'iekkakukkah этот цветок</li></ol>"
)

DOID_HTML = (
    "<b>doid'i||e</b> <i>v</i> <ol>"
    "<li> дойти, добраться до какого-л. места; доходить, доставать до чего-л.; "
    "ildah šuat ~ kül'äh добраться</li>"
    "<li> <i>перен.</i> доходить до ума, до сердца, вызывать отклик, мысли; "
    "pagina ei ~n piäh разговор</li></ol>"
)

OLLA_HTML = (
    "<b>olla</b> <i>v</i> <ol>"
    "<li> быть (в функции глагола-связки); существовать; "
    "impersonale: есть, имеется</li></ol>"
)

A_HTML = (
    "<b>a</b> <ol>"
    "<li> <i>conj</i> а, но <i>(при противопоставлении предложений)</i>; "
    "ket mis'sä, a müö koissa кто где, а мы дома</li>"
    "<li> <i>particl</i> а; a pelvašta kül'vet't'ih vähiin ну а льна сеяли помалу; "
    "a Roštuošta l'äht'iet'äh zbornoit а с Рождества пойдут сборища</li>"
    "<li> <i>interj</i> а – а; a – a, mäne kunne mahat! а иди куда хочешь!; "
    "a – a nu šilmaš, valehiččua а ну, тебя, враля</li>"
    "</ol>"
)

ABEWK_HTML = (
    "<b>abewkšissa</b> <i>adv</i>: olla ~ быть в обиде, печали; "
    "jäi vunukka kod'ih ~, vanhemmat ei otettu mel'l'ičäl'l'ä "
    "внук остался дома в обиде: старшие не взяли [его] на мельницу"
)

LIS_HTML = (
    "<b>l'is'||t'ie</b> <ol>"
    "<li>очищать, разравнивать полосы бересты, лыка; <i>ср.</i> parroštua</li>"
    "<li>обрезать перья лука, обрывать ботву, листья; luwkat ~s'it illustration</li>"
    "<li><i>см.</i> l'is's'e</li></ol>"
)

LIS_FULL_HTML = (
    "<b>l'is'||t'ie</b> <i>v</i> <ol>"
    "<li>очищать, разравнивать полосы бересты, лыка, лучины для плетения "
    "лаптей, корзин и пр.; <i>ср.</i> parroštua</li>"
    "<li>обрезать перья лука, обрывать ботву, листья; illustration</li>"
    "<li><i>см.</i> l'is's'e</li></ol>"
)

MANNA_PHRASEME_HTML = (
    "<b>män||nä</b> <ol>"
    "<li>идти на лад, получаться; ◊ miehel'lä ~ выйти замуж; "
    "t'üt't'äret вышли замуж</li></ol>"
)

PANNA_ADDENDUM_HTML = (
    "<ol start='10'><li>вступать в половую связь "
    "<i>(о мужчине или самце животного)</i></li></ol>"
)


class GlossSensesFromHtmlTestCase(SimpleTestCase):
    def test_mai_jata_two_senses_no_karelian(self):
        senses = gloss_senses_from_html(MAI_HTML)
        self.assertEqual(len(senses), 2)
        self.assertIn("отдавать", senses[0])
        self.assertIn("по вкусу", senses[0])
        self.assertIn("быть схожим", senses[1])
        self.assertIn("смахивать", senses[1])
        self.assertNotRegex(senses[1], r"[A-Za-z]")

    def test_doid_two_senses_including_peren(self):
        senses = gloss_senses_from_html(DOID_HTML)
        self.assertEqual(len(senses), 2)
        self.assertIn("добраться", senses[0])
        self.assertIn("перен", senses[1].lower())
        self.assertIn("до сердца", senses[1])
        self.assertIn("вызывать отклик", senses[1])

    def test_olla_gloss_strips_grammar_paren_and_latin_tail(self):
        senses = gloss_senses_from_html(OLLA_HTML)
        self.assertEqual(len(senses), 1)
        self.assertIn("быть", senses[0])
        self.assertIn("существовать", senses[0])
        self.assertIn("имеется", senses[0])
        self.assertNotIn("функции", senses[0])
        self.assertNotRegex(senses[0], r"[A-Za-z]")

    def test_a_service_word_gloss_without_illustrations(self):
        senses = gloss_senses_from_html(A_HTML)
        self.assertEqual(len(senses), 3)
        self.assertIn("а", senses[0])
        self.assertIn("но", senses[0])
        self.assertEqual(senses[1], "а")
        self.assertEqual(senses[2], "а – а")
        joined = " ".join(senses).lower()
        self.assertNotIn("иди", joined)
        self.assertNotIn("хочешь", joined)
        self.assertNotIn("льна", joined)
        self.assertNotRegex(joined, r"[A-Za-z]")

    def test_abewk_single_block_spaced_tilde_gloss(self):
        senses = gloss_senses_from_html(ABEWK_HTML)
        self.assertEqual(len(senses), 1)
        self.assertIn("быть в обиде", senses[0])
        self.assertIn("быть в печали", senses[0])
        self.assertNotIn("мельниц", senses[0])
        self.assertNotRegex(senses[0], r"[A-Za-z]")

    def test_lis_skips_sm_crossref_li(self):
        senses = gloss_senses_from_html(LIS_HTML)
        self.assertEqual(len(senses), 2)
        joined = " ".join(senses).lower()
        self.assertNotIn("см.", joined)
        self.assertIn("очищать", senses[0])
        self.assertIn("обрывать", senses[1])

    def test_manna_cuts_phraseme_after_lozenge(self):
        senses = gloss_senses_from_html(MANNA_PHRASEME_HTML)
        self.assertEqual(len(senses), 1)
        self.assertIn("идти на лад", senses[0])
        self.assertIn("получаться", senses[0])
        self.assertNotIn("выйти замуж", senses[0])


class DropSubsumedAuxTestCase(SimpleTestCase):
    def test_drops_be_when_phrase_exists(self):
        raw = ["быть", "быть схожим", "напоминать"]
        self.assertEqual(
            _drop_subsumed_auxiliaries(raw),
            ["быть схожим", "напоминать"],
        )

    def test_drops_vyizyvat_when_phrase_exists(self):
        raw = ["вызывать", "вызывать отклик", "доходить до ума"]
        self.assertEqual(
            _drop_subsumed_auxiliaries(raw),
            ["вызывать отклик", "доходить до ума"],
        )

    def test_keeps_be_for_olla_like_lists(self):
        raw = ["быть", "существовать"]
        self.assertEqual(_drop_subsumed_auxiliaries(raw), raw)

    def test_keeps_be_when_gloss_lists_it_alongside_phrases(self):
        gloss = [
            "быть, существовать",
            "находиться, быть в каком-л. состоянии, быть кем-л.",
            "быть, иметься",
        ]
        raw = [
            "быть",
            "существовать",
            "находиться",
            "быть в каком-л. состоянии",
            "быть кем-л.",
            "иметься",
        ]
        self.assertEqual(_drop_subsumed_auxiliaries(raw, gloss), raw)


class TranslationCleanupPromptTestCase(TestCase):
    def test_prompt_mentions_gloss_senses(self):
        self.assertIn("gloss_senses", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("доходить до сердца", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("крупного сома", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("корзин и пр.", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)

    def test_build_cleanup_input_includes_gloss(self):
        art = Article.objects.create(word="mai||jata", article_html=MAI_HTML)
        ArticleIndexTranslate.objects.create(article=art, rus_word="быть")
        payload = build_cleanup_input(art)
        self.assertEqual(len(payload["gloss_senses"]), 2)
        self.assertIn("быть схожим", payload["gloss_senses"][1])
        self.assertEqual(payload["addendum_gloss_senses"], [])

    def test_build_cleanup_input_includes_addendum_gloss(self):
        art = Article.objects.create(
            word="pan||na",
            article_html="<b>pan||na</b> <ol><li>варить пиво</li></ol>",
        )
        ArticleAddition.objects.create(article=art, article_html=PANNA_ADDENDUM_HTML)
        ArticleIndexTranslate.objects.create(article=art, rus_word="варить")
        payload = build_cleanup_input(art)
        self.assertEqual(len(payload["gloss_senses"]), 1)
        self.assertIn("варить пиво", payload["gloss_senses"][0])
        self.assertEqual(len(payload["addendum_gloss_senses"]), 1)
        self.assertIn("половую связь", payload["addendum_gloss_senses"][0])
        self.assertIn("addendum_gloss_senses", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)

    def test_service_word_detected_from_pos_tag(self):
        art = Article.objects.create(word="a")
        tag = Tag.objects.create(tag="conj", name="союз", type=2)
        ArticleIndexTag.objects.create(article=art, tag=tag)
        ArticleIndexTranslate.objects.create(article=art, rus_word="и")
        payload = build_cleanup_input(art)
        self.assertTrue(payload["is_service_word"])
        self.assertTrue(is_service_word_article(pos_tags_for(art)))


class ParseCleanupJsonTestCase(SimpleTestCase):
    def test_parses_wrapped_json(self):
        text = '```json\n{"translations": ["быстрый", "скорый"]}\n```'
        raw = parse_cleanup_json(text)
        self.assertEqual(raw, ["быстрый", "скорый"])


class SanitizeCleanedTranslationsTestCase(SimpleTestCase):
    def test_sanitize_applies_aux_drop(self):
        raw = ["вызывать", "вызывать отклик"]
        self.assertEqual(
            sanitize_cleaned_translations(raw),
            ["вызывать отклик"],
        )

    def test_strips_grammar_parens_keeps_semantic(self):
        raw = [
            "быть (в функции глагола-связки)",
            "отдавать (по вкусу)",
        ]
        self.assertEqual(
            sanitize_cleaned_translations(raw),
            ["быть", "отдавать (по вкусу)"],
        )

    def test_strip_grammar_parens_only(self):
        self.assertEqual(
            _strip_grammar_parens("быть (в функции глагола-связки)"),
            "быть",
        )
        self.assertEqual(
            _strip_grammar_parens("отдавать (по вкусу)"),
            "отдавать (по вкусу)",
        )

    def test_expands_bare_comparative_with_shared_verb(self):
        raw = [
            "облегчить",
            "делать более лёгким",
            "менее трудным",
            "отпускать боли",
        ]
        self.assertEqual(
            sanitize_cleaned_translations(raw),
            [
                "облегчить",
                "делать более легким",
                "делать менее трудным",
                "отпускать боли",
            ],
        )

    def test_normalize_yo_to_e_for_search(self):
        self.assertEqual(
            sanitize_cleaned_translations(["придётся", "лёгкий"]),
            ["придется", "легкий"],
        )

    def test_drops_sm_crossref_from_llm_output(self):
        raw = [
            "разравнивать полосы лыка",
            "обрывать листья",
            "см. ' ' '",
        ]
        gloss = gloss_senses_from_html(LIS_HTML)
        self.assertEqual(
            sanitize_cleaned_translations(raw, gloss_senses=gloss),
            ["разравнивать полосы лыка", "обрывать листья"],
        )

    def test_phraseme_senses_from_lozenge_block(self):
        from translation_cleanup import _phraseme_senses_from_html

        senses = _phraseme_senses_from_html(MANNA_PHRASEME_HTML)
        self.assertIn("выйти замуж", senses)
        self.assertEqual(
            sanitize_cleaned_translations(
                ["идти на лад", "получаться", "выйти замуж"],
                gloss_senses=gloss_senses_from_html(MANNA_PHRASEME_HTML),
            ),
            ["идти на лад", "получаться", "выйти замуж"],
        )

    def test_service_word_filter_drops_illustration_phrases(self):
        gloss = [
            "а, но (при противопоставлении предложений)",
            "а",
            "а – а",
        ]
        raw = [
            "а",
            "но",
            "ну а",
            "а иди куда хочешь",
            "а ну",
            "а – а",
        ]
        self.assertEqual(
            sanitize_cleaned_translations(raw, is_service_word=True, gloss_senses=gloss),
            ["а", "но", "а – а"],
        )

    def test_service_word_preserves_original_single_word_not_in_gloss(self):
        """da I: «но» in index but absent from gloss / LLM output."""
        gloss = ["да", "и"]
        raw = ["да", "и"]
        original = ["да", "и", "но"]
        self.assertEqual(
            sanitize_cleaned_translations(
                raw,
                is_service_word=True,
                gloss_senses=gloss,
                original_translations=original,
            ),
            ["да", "и", "но"],
        )

    def test_service_word_does_not_restore_illustration_phrases_from_original(self):
        gloss = ["а, но (при противопоставлении предложений)", "а", "а – а"]
        raw = ["а", "но", "а – а"]
        original = ["а", "но", "а – а", "ну а", "а иди куда хочешь"]
        self.assertEqual(
            sanitize_cleaned_translations(
                raw,
                is_service_word=True,
                gloss_senses=gloss,
                original_translations=original,
            ),
            ["а", "но", "а – а"],
        )

    def test_olla_sanitize_restores_be_from_gloss(self):
        gloss = [
            "быть, существовать",
            "находиться, быть в каком-л. состоянии, быть кем-л.",
            "быть, иметься",
        ]
        raw = [
            "существовать",
            "находиться",
            "быть в каком-л. состоянии",
            "быть кем-л.",
            "иметься",
        ]
        result = sanitize_cleaned_translations(raw, gloss_senses=gloss)
        lowered = [t.lower() for t in result]
        self.assertIn("быть", lowered)
        self.assertIn("существовать", lowered)
        self.assertIn("иметься", lowered)

    def test_abewk_sanitize_drops_bare_pechali(self):
        gloss = gloss_senses_from_html(ABEWK_HTML)
        raw = ["быть в обиде", "быть в печали", "печали"]
        self.assertEqual(
            sanitize_cleaned_translations(raw, gloss_senses=gloss),
            ["быть в обиде", "быть в печали"],
        )

    def test_diff_translations(self):
        d = diff_translations(["быть", "был"], ["быть"])
        self.assertEqual(d["removed"], ["был"])


class IProParallelSanitizeTestCase(SimpleTestCase):
    def test_expands_luchiny_parallel_from_gloss(self):
        gloss = gloss_senses_from_html(LIS_FULL_HTML)
        raw = [
            "очищать",
            "разравнивать полосы лыка",
            "лучины для плетения лаптей",
            "корзин и пр.",
            "обрезать перья лука",
            "обрывать листья",
        ]
        result = sanitize_cleaned_translations(raw, gloss_senses=gloss)
        lowered = [t.lower() for t in result]
        self.assertIn("очищать", lowered)
        self.assertIn("лучины для плетения корзин", lowered)
        self.assertNotIn("корзин и пр.", lowered)
        self.assertNotIn("корзин и пр", lowered)

    def test_phrases_from_i_pro_parallel_helper(self):
        from translation_cleanup import _phrases_from_i_pro_parallel

        phrases = _phrases_from_i_pro_parallel(
            ["лучины для плетения лаптей, корзин и пр."]
        )
        self.assertIn("лучины для плетения лаптей", phrases)
        self.assertIn("лучины для плетения корзин", phrases)
