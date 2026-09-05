from django.test import SimpleTestCase, TestCase
from translation_cleanup import (
    SYSTEM_PROMPT_CLEAN_TRANSLATIONS,
    SYSTEM_PROMPT_REVIEW_TRANSLATIONS,
    _drop_subsumed_auxiliaries,
    _strip_grammar_parens,
    build_cleanup_input,
    build_cleanup_review_user_prompt,
    clear_dict_label_prefix_cache,
    diff_translations,
    gloss_senses_from_html,
    is_service_word_article,
    parse_cleanup_json,
    pos_roles_for,
    pos_tags_for,
    sanitize_cleaned_translations,
    set_dict_label_tokens_for_tests,
)

from dict.models import (
    Article,
    ArticleAddition,
    ArticleIndexTag,
    ArticleIndexTranslate,
    Tag,
)

# Tag.type 3+4 snapshot for SimpleTestCase (no DB). Keep in sync with prod Tag.
_TEST_DICT_LABEL_TAGS = [
    "арх.",
    "бот.",
    "бранн.",
    "груб.",
    "детск.",
    "зоол.",
    "ирон.",
    "миф.",
    "неодобр.",
    "перен.",
    "поэт.",
    "пренебр.",
    "примета",
    "религ.",
    "стр.",
    "с.-х.",
    "техн.",
    "ткац.",
    "флк.",
    "шутл.",
    "этн.",
    "всг.",
]


class _DictLabelTokensMixin:
    """Pin dict labels so SimpleTestCase does not query Tag."""

    def setUp(self):
        set_dict_label_tokens_for_tests(_TEST_DICT_LABEL_TAGS)

    def tearDown(self):
        set_dict_label_tokens_for_tests(None)


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

LIETA_HTML = (
    "<b>l’ie||t’ä</b> <i>v</i> <ol>"
    "<li>быть, стать, становиться <i>(в значении будущего времени употребляется "
    "в форме 3л. ед.ч. l’ienöw, возможна краткая форма — l’iew)</i>; "
    "väl’iän ~t’äh t’ipazet скоро будут <i>(вылупляться)</i> цыплята; "
    "čiepis’s’ä koira ~w pattie на цепи собака станет злой</li>"
    "<li>придётся <i>(в сочетании с инфинитивом)</i>; "
    "hein’iä viel’ä ~nöw oštua сена придётся ещё покупать</li>"
    "<li>хватит, достаточно; ~nöw t’eil’ä it’kie! будет вам плакать!</li>"
    "</ol>"
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

DENGak_HTML = (
    "<b>d'engak||aš</b> <i>a</i> денежный, имеющий деньги; "
    "hiän n'üt ~kahalla ruavolla on он теперь на денежной работе; "
    "ken mahtaw el'ia, že on ~ кто умеет жить, тот денежный"
)

KORVA_HTML = (
    "<b>korv||a I</b> <i>s</i>\n<ol>\n"
    "  <li>~an'e ухо; šuwret ~at большие уши; korhistua ~at навострить уши, "
    "прислушаться; ~ kuwlow, šil'mä n'ägöw, a šiämi čusvuiččow <i>флк.</i> "
    "ухо слышит, глаз видит, а сердце чувствует;\n"
    "    ~at vuwvetah zolotuhua уши текут от золотухи </li>\n"
    "  <li>~an'e ручка, ухо, ушко <i>(у разных предметов)</i>; "
    "kellon ~ ухо колокола; korvon ~at уши ушата; otti samvuaran ~ista "
    "он взял самовар за ручки</li>\n"
    "  <li>место около чего-л.; olla oven ~ašša быть у дверей, "
    "быть на пороге ◊ l'äbi ~ista мимо ушей</li>\n"
    "</ol>"
)

KORVA_UNICODE_HTML = KORVA_HTML.replace("an'e", "an\u2019e").replace(
    "n'ägöw", "n\u2019ägöw"
)

PAHNA_HTML = (
    "<b>pahna</b> <i>s</i> логово, лежбище, лёжка зверя; kondien ~ берлога медведя; "
    "šijan ~ лёжка свиньи; šuon tagana on hukin ~ за болотом логово волков; "
    "mužikat noššettih kondien ~šta мужики подняли медведя из берлоги; "
    "šiga kun roiččiečow ~šša, n'in vihma l'iew <i>примета</i> "
    "свинья в лёжке роется: быть дождю"
)

MIELI_HTML = (
    "<b>miel'||i</b> <i>s</i><ol>"
    "<li>ум, разум; pien'en lapšen ~ ум малолетнего ребёнка</li>"
    "<li>мысль, намерение; t'äšt'ä mat'erjašta on ~ ommella pal'to</li>"
    "<li>настроение, душевное состояние; hüvä ~ хорошее настроение; "
    "t'üt'öt kuwnellah hüväl'l'ä ~iin</li>"
    "<li>память; воспоминание; muistuo ~eh помнить</li>"
    "<li>душа; нрав; t'ämä paikkan'e miwla ~d'ä müöt'</li>"
    "</ol>"
)

DOROGA_HTML = (
    "<b>dorog||a</b> <i>s</i> дорога, путь; pit'kä ~ длинная дорога; "
    "kohal'l'in'e ~ прямая дорога; pöwrün jäl'geh ~at oldih ummet "
    "после метели дороги были занесены снегом"
)

SHILMA_HTML = (
    "<b>šil'm||ä, ~än'e</b> <i>s</i> <ol>"
    "<li>глаз; harmuat ~ät серые глаза; ei kaikki šuwh, mid'ä n'ägöw ~ "
    "<i>флк.</i> не все в рот, что глаз видит </li>"
    "<li>ушко, отверстие, ячея; n'ieglan ~än'e игольное ушко</li>"
    "<li>окно <i>(в болоте, трясине)</i>; "
    "◊ paha ~ дурной глаз; peššä ~ät умыться; "
    "~is's'ä на глазах, на виду</li>"
    "</ol>"
)

AIGANA_HTML = (
    "<b>aigana</b> <i>adv</i> в присутствии кого-л., при ком-л., перед кем-л.; "
    "mužikoin aigana myö emmä pagize karielakši при мужьях мы не "
    "разговариваем по-карельски;"
)

KRUASKA_HTML = (
    "<b>kruask||a</b> <i>s</i> краска; ~ keldan\u2019e жёлтая краска; "
    "~ua oššiin, pid'äw langat painua я купила краски, надо нитки покрасить; "
    "voi vanhen'i: pid'äw ~ah keit't'iä масло прогоркло: надо с краской переварить"
)

JALGA_HTML = (
    "<b>jalga</b> <i>s</i> <ol>"
    "<li> нога <i>(человека, животного);</i> šeizawduo jalloilla встать на ноги; "
    "<i>ср.</i> šorka </li>"
    "<li> <i>техн.</i> нога, опора; kerinlawvat pandu jаllаllа воробы "
    "поставлены на опору ◊ potkai jallat отбило ноги; nowšša jalloilla "
    "стать самостоятельным; выбиться из нужды</li>"
    "</ol>"
)

JALGA_HIINA_HTML = (
    "<b>jalga|hiina</b> <i>s</i> верёвка, привязанная к люльке для качания её ногой; "
    "käz'il'l'ä mid'äigi ruat, a l'ekutat kät'üt't'ä ~hiinašta руками что-либо "
    "делаешь, а люльку за верёвку качаешь"
)

JANDU_HTML = (
    "<b>jandu||o</b> <i>v</i> усиливаться, становиться беспрерывным "
    "<i>(о каком-л. действии);</i> jandu vihmumah стало беспрерывно дождить; "
    "hammaš jandu kivis't'ämäh зуб болит беспрерывно; "
    "akka šanow: lapšella ~n šuwri üönit'et't'äjä ворожея говорит; "
    "у ребёнка запущенная большая плакса <i>(болезнь);</i> "
    "l'eččimät'öin kibu ~w <i>флк.</i> невылеченная боль скажется"
)

LIAGA_SEE_ONLY_HTML = (
    "<b>l'iägä</b> <i>s</i> <i>всг.</i> <i>см.</i> l'iäžö; "
    "ut'at ~ššä uijah утята плавают в луже"
)

JALGIN_LAWDA_HTML = (
    "<b>jalgin|lawda</b> <i>s</i> коник, широкая доска, прилегающая к печке, "
    "для удобства спуска и подъема на неё; "
    "valmis' šolahtua kiwgualda ~lawvalla он готов спуститься с печки на коник"
)


AJEL_HTML = (
    "<b>ajel||la</b> <i>v</i> <ol>"
    "<li> <i>freq</i> от ajua 1, 2; huomena ~ stančalla съездить завтра на станцию; "
    "l'ien' i pühäkeški, ruvettih ~omah suatot наступил мясоед, начали ходить сватать</li>"
    "<li> <i>см.</i> ajatella; korkat piiraih ~et, panet šiän'd'ä "
    "раскатаешь корки для пирогов, положишь начинку </li>"
    "<li> проходить плугом, бороной, оставляя след; ~ vavot нарезать борозды; "
    "pehmie mua on, n'in kahteh piih ~et земля мягкая, так на два следа проборонишь</li>"
    "</ol>"
)


class GlossSensesFromHtmlTestCase(_DictLabelTokensMixin, SimpleTestCase):
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
        self.assertNotIn("перен", senses[1].lower())
        self.assertIn("до сердца", senses[1])
        self.assertIn("вызывать отклик", senses[1])

    def test_jalga_keeps_parens_strips_tehn(self):
        senses = gloss_senses_from_html(JALGA_HTML)
        self.assertEqual(senses[0], "нога (человека, животного)")
        self.assertEqual(senses[1], "нога, опора")
        self.assertNotIn("техн", " ".join(senses).lower())

    def test_strips_regional_dialect_labels_in_gloss_only(self):
        """Dialect marks are Tag.type=4; stripping is LLM duty (sanitize is ё→е only)."""
        from translation_cleanup import (
            _strip_leading_pos_label,
            set_dict_label_tokens_for_tests,
        )

        set_dict_label_tokens_for_tests(["всг.", "перен.", "техн."])
        self.assertEqual(
            _strip_leading_pos_label("всг. полка в избе от печи к стене"),
            "полка в избе от печи к стене",
        )

    def test_jalga_hiina_keeps_attributive_comma_phrase(self):
        senses = gloss_senses_from_html(JALGA_HIINA_HTML)
        self.assertEqual(
            senses,
            ["веревка, привязанная к люльке для качания ее ногой"],
        )
        cleaned = sanitize_cleaned_translations(
            ["веревка, привязанная к люльке для качания ее ногой"],
            gloss_senses=senses,
        )
        self.assertEqual(
            cleaned,
            ["веревка, привязанная к люльке для качания ее ногой"],
        )

    def test_jandu_stops_gloss_at_first_karelian_example(self):
        senses = gloss_senses_from_html(JANDU_HTML)
        self.assertEqual(len(senses), 1)
        gloss = senses[0].lower()
        self.assertIn("усиливаться", gloss)
        self.assertIn("становиться беспрерывным", gloss)
        self.assertNotIn("плакса", gloss)
        self.assertNotIn("ворожея", gloss)
        self.assertNotIn("дождить", gloss)

    def test_see_only_article_has_no_gloss_no_index(self):
        senses = gloss_senses_from_html(LIAGA_SEE_ONLY_HTML)
        self.assertEqual(senses, [])

    def test_jalgin_lawda_keeps_attributive_purpose_chain(self):
        senses = gloss_senses_from_html(JALGIN_LAWDA_HTML)
        self.assertEqual(len(senses), 1)
        self.assertIn("прилегающая к печке", senses[0])
        self.assertIn("для удобства", senses[0])

    def test_olla_gloss_strips_grammar_paren_and_latin_tail(self):
        senses = gloss_senses_from_html(OLLA_HTML)
        self.assertEqual(len(senses), 1)
        self.assertIn("быть", senses[0])
        self.assertIn("существовать", senses[0])
        self.assertIn("имеется", senses[0])
        self.assertNotIn("функции", senses[0])
        self.assertNotRegex(senses[0], r"[A-Za-z]")

    def test_lieta_keeps_byt_stat_stanovitsya_despite_paradigm_note(self):
        """Karelian forms inside grammar (… l’ienöw …) must not wipe sense 1."""
        senses = gloss_senses_from_html(LIETA_HTML)
        self.assertEqual(len(senses), 3)
        self.assertIn("быть", senses[0])
        self.assertIn("стать", senses[0])
        self.assertIn("становиться", senses[0])
        self.assertNotIn("l’ienöw", senses[0].lower())
        self.assertNotIn("будущ", senses[0].lower())
        self.assertNotIn("цыплят", senses[0].lower())
        self.assertNotIn("станет", senses[0].lower())
        self.assertIn("придется", senses[1])
        self.assertIn("хватит", senses[2])
        self.assertIn("достаточно", senses[2])
        self.assertNotIn("плакать", " ".join(senses).lower())

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
        self.assertNotIn("идти на получаться", senses[0])

    def test_manna_parallel_infinitives_in_gloss(self):
        senses = gloss_senses_from_html(MANNA_PHRASEME_HTML)
        self.assertIn("идти на лад", senses[0])
        self.assertIn("получаться", senses[0])
        self.assertNotIn("идти на получаться", senses[0])

    def test_dengak_skips_illustration_after_spaced_tilde(self):
        senses = gloss_senses_from_html(DENGak_HTML)
        self.assertEqual(senses, ["денежный, имеющий деньги"])
        joined = " ".join(senses).lower()
        self.assertNotIn("кто умеет жить", joined)
        self.assertNotIn("денежной работе", joined)

    def test_korva_ol_three_senses_without_illustrations(self):
        senses = gloss_senses_from_html(KORVA_HTML)
        self.assertEqual(len(senses), 3)
        self.assertEqual(senses[0], "ухо")
        self.assertIn("ручка", senses[1])
        self.assertIn("ухо", senses[1])
        self.assertIn("ушко", senses[1])
        self.assertNotIn("ухо колокола", senses[1])
        self.assertEqual(senses[2], "место около чего-л.")
        joined = " ".join(senses).lower()
        self.assertNotIn("слышит", joined)
        self.assertNotIn("самовар", joined)
        self.assertNotIn("мимо ушей", joined)
        self.assertNotRegex(joined, r"[A-Za-z]")

    def test_korva_unicode_apostrophe_gloss(self):
        senses = gloss_senses_from_html(KORVA_UNICODE_HTML)
        self.assertEqual(senses[0], "ухо")
        self.assertIn("ухо", senses[1])
        self.assertIn("ручка", senses[1])
        self.assertNotIn("ухо колокола", senses[1])
        self.assertEqual(senses[2], "место около чего-л.")

    def test_korva_gloss_lists_ushko(self):
        senses = gloss_senses_from_html(KORVA_UNICODE_HTML)
        self.assertIn("ушко", " ".join(senses).lower())
        self.assertIn("ручка", " ".join(senses).lower())

    def test_pahna_gloss_without_possessive_collocations(self):
        senses = gloss_senses_from_html(PAHNA_HTML)
        self.assertEqual(len(senses), 1)
        gloss = senses[0].lower()
        self.assertIn("логово", gloss)
        self.assertIn("лежбище", gloss)
        self.assertIn("лежка зверя", gloss)
        self.assertNotIn("берлога медведя", gloss)
        self.assertNotIn("лежка свиньи", gloss)
        self.assertNotIn("логово волков", gloss)
        self.assertNotIn("мужики подняли", gloss)
        self.assertNotRegex(gloss, r"[A-Za-z]")

    def test_mieli_gloss_without_evaluative_adj_noun(self):
        senses = gloss_senses_from_html(MIELI_HTML)
        self.assertEqual(len(senses), 5)
        joined = " | ".join(senses).lower()
        self.assertIn("настроение", joined)
        self.assertIn("душевное состояние", joined)
        self.assertNotIn("хорошее настроение", joined)

    def test_doroga_drops_adj_noun_after_karelian_tilde(self):
        """pit'kä ~ длинная дорога — illustration, not gloss (same as olut)."""
        senses = gloss_senses_from_html(DOROGA_HTML)
        joined = " | ".join(senses).lower()
        self.assertIn("дорога", joined)
        self.assertIn("путь", joined)
        self.assertNotIn("длинная дорога", joined)
        self.assertNotIn("прямая дорога", joined)
        self.assertNotIn("после метели", joined)

    def test_kruaska_drops_color_adj_illustration(self):
        senses = gloss_senses_from_html(KRUASKA_HTML)
        joined = " ".join(senses).lower()
        self.assertNotIn("желтая краска", joined)
        self.assertNotIn("жёлтая краска", joined)

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
    def setUp(self):
        set_dict_label_tokens_for_tests(None)
        clear_dict_label_prefix_cache()

    def tearDown(self):
        set_dict_label_tokens_for_tests(None)
        clear_dict_label_prefix_cache()

    def test_prompt_mentions_gloss_senses(self):
        self.assertIn("gloss_senses", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("dict_labels", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("pos —", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("доходить до сердца", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("крупного сома", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("корзин и пр.", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("другач", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("вывихивать руку", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("V (X, Y)", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("Gloss vs иллюстрация", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("пример НЕ отменяет", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("дойти", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("вбирать", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("впитывать в себя жидкость", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("очищать", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("Краткий однословный V-вершина", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn(
            "НЕ заменяет и НЕ отменяет краткую", SYSTEM_PROMPT_CLEAN_TRANSLATIONS
        )
        self.assertIn("Неверно:", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("=== ПРИМЕРЫ ===", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)

    def test_review_prompt_covers_parallel_and_ellipsis(self):
        self.assertIn("draft_translations", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("другач", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("доходить до сердца", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("ЧАСТЬ РЕЧИ (pos)", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("вершина", SYSTEM_PROMPT_REVIEW_TRANSLATIONS.lower())
        self.assertIn("очищать лучины", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("original_translations", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("ОБЯЗАТЕЛЬНАЯ ПРОВЕРКА", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn(
            "Развёрнутая строка НЕ заменяет", SYSTEM_PROMPT_REVIEW_TRANSLATIONS
        )
        self.assertIn("ИСПРАВЬ", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("вбирать", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("впитывать", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("дойти", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("вывихивать руку", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("V (X, Y)", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("нога человека", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("N (A, B)", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("нога, опора", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("Gloss vs иллюстрация", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("пример его не отменяет", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        self.assertIn("=== ПРИМЕРЫ ===", SYSTEM_PROMPT_REVIEW_TRANSLATIONS)
        prompt = build_cleanup_review_user_prompt(
            {
                "word": "x",
                "pos": "существительное",
                "pos_tags": [],
                "is_service_word": False,
                "dict_labels": [],
                "gloss_senses": ["пиво из сусла второго слива, другач"],
                "addendum_gloss_senses": [],
                "translations": ["пиво из сусла второго другач"],
            },
            ["пиво из сусла второго другач"],
        )
        self.assertIn("draft_translations", prompt)
        self.assertIn("другач", prompt)

    def test_pos_role_from_type2_tag(self):
        art = Article.objects.create(word="ajua", article_html="<b>ajua</b>")
        ArticleIndexTranslate.objects.create(article=art, rus_word="ехать")
        v = Tag.objects.create(tag="v", name="verbum, глагол", type=2)
        f = Tag.objects.create(tag="freq", name="frequentativum", type=2)
        ArticleIndexTag.objects.create(article=art, tag=v)
        ArticleIndexTag.objects.create(article=art, tag=f)
        clear_dict_label_prefix_cache()
        self.assertEqual(pos_roles_for(art), ["глагол"])
        payload = build_cleanup_input(art)
        self.assertEqual(payload["pos"], "глагол")
        self.assertTrue(any("глагол" in (t or "").lower() for t in payload["pos_tags"]))

    def test_pos_role_noun(self):
        art = Article.objects.create(word="olut", article_html="<b>olut</b> пиво")
        ArticleIndexTranslate.objects.create(article=art, rus_word="пиво")
        tag = Tag.objects.create(
            tag="s", name="substantivum, имя существительное", type=2
        )
        ArticleIndexTag.objects.create(article=art, tag=tag)
        self.assertEqual(pos_roles_for(art), ["существительное"])
        self.assertEqual(build_cleanup_input(art)["pos"], "существительное")
        self.assertIn("например", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("гнать деготь", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)
        self.assertIn("охочий", SYSTEM_PROMPT_CLEAN_TRANSLATIONS)

    def test_build_cleanup_input_includes_gloss(self):
        art = Article.objects.create(word="mai||jata", article_html=MAI_HTML)
        ArticleIndexTranslate.objects.create(article=art, rus_word="быть")
        payload = build_cleanup_input(art)
        self.assertEqual(len(payload["gloss_senses"]), 2)
        self.assertIn("быть схожим", payload["gloss_senses"][1])
        self.assertEqual(payload["addendum_gloss_senses"], [])
        self.assertIn("dict_labels", payload)

    def test_build_cleanup_input_dict_labels_from_tag(self):
        Tag.objects.create(tag="всг.", name="весьегонский говор", type=4)
        Tag.objects.create(tag="перен.", name="переносно", type=3)
        Tag.objects.create(tag="s", name="substantivum", type=2)
        clear_dict_label_prefix_cache()
        art = Article.objects.create(word="x", article_html="<b>x</b> тест")
        ArticleIndexTranslate.objects.create(article=art, rus_word="тест")
        payload = build_cleanup_input(art)
        self.assertEqual(set(payload["dict_labels"]), {"всг.", "перен."})

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

    def test_build_cleanup_input_excludes_phrasemes(self):
        art = Article.objects.create(word="män||nä", article_html=MANNA_PHRASEME_HTML)
        ArticleIndexTranslate.objects.create(article=art, rus_word="идти на лад")
        payload = build_cleanup_input(art)
        self.assertNotIn("phraseme_senses", payload)
        self.assertNotIn("выйти замуж", " ".join(payload["gloss_senses"]))

    def test_service_word_detected_from_pos_tag(self):
        art = Article.objects.create(word="a")
        tag = Tag.objects.create(tag="conj", name="союз", type=2)
        ArticleIndexTag.objects.create(article=art, tag=tag)
        ArticleIndexTranslate.objects.create(article=art, rus_word="и")
        payload = build_cleanup_input(art)
        self.assertTrue(payload["is_service_word"])
        self.assertTrue(is_service_word_article(pos_tags_for(art)))


class ParseCleanupJsonTestCase(_DictLabelTokensMixin, SimpleTestCase):
    def test_parses_wrapped_json(self):
        text = '```json\n{"translations": ["быстрый", "скорый"]}\n```'
        raw = parse_cleanup_json(text)
        self.assertEqual(raw, ["быстрый", "скорый"])


class SanitizeCleanedTranslationsTestCase(_DictLabelTokensMixin, SimpleTestCase):
    """Sanitize is ё→е + trim/dedupe only; phrase cleanup is LLM responsibility."""

    def test_normalize_yo_to_e_for_search(self):
        self.assertEqual(
            sanitize_cleaned_translations(["придётся", "лёгкий"]),
            ["придется", "легкий"],
        )

    def test_yo_deduped_case_insensitive(self):
        self.assertEqual(
            sanitize_cleaned_translations(["Лёгкий", "легкий", "лёгкий"]),
            ["Легкий"],
        )

    def test_passthrough_keeps_llm_phrases(self):
        raw = [
            "хвост",
            "конечная часть чего-л.",
            "коровий хвост",
            "тряпка, намотанная на большой палец",
            "овсяной блин, свернутый в трубочку",
            "до сердца",
            "техн. опора",
            "всг. полка",
        ]
        self.assertEqual(
            sanitize_cleaned_translations(raw),
            [
                "хвост",
                "конечная часть чего-л.",
                "коровий хвост",
                "тряпка, намотанная на большой палец",
                "овсяной блин, свернутый в трубочку",
                "до сердца",
                "техн. опора",
                "всг. полка",
            ],
        )

    def test_strip_grammar_parens_helper_still_works(self):
        self.assertEqual(
            _strip_grammar_parens("быть (в функции глагола-связки)"),
            "быть",
        )
        self.assertEqual(
            _strip_grammar_parens("отдавать (по вкусу)"),
            "отдавать (по вкусу)",
        )
        self.assertEqual(
            _strip_grammar_parens(
                "становиться (в значении будущего времени употребляется "
                "в форме 3л. ед.ч. l’ienöw, возможна краткая форма — l’iew)"
            ),
            "становиться",
        )

    def test_diff_translations(self):
        d = diff_translations(["быть", "был"], ["быть"])
        self.assertEqual(d["removed"], ["был"])

    def test_rejects_non_list(self):
        self.assertIsNone(sanitize_cleaned_translations("x"))

    def test_drops_empty_strings(self):
        self.assertEqual(sanitize_cleaned_translations(["а", "", "  "]), ["а"])


class IProParallelSanitizeTestCase(_DictLabelTokensMixin, SimpleTestCase):
    def test_phrases_from_i_pro_parallel_helper(self):
        from translation_cleanup import _phrases_from_i_pro_parallel

        phrases = _phrases_from_i_pro_parallel(
            ["лучины для плетения лаптей, корзин и пр."]
        )
        self.assertIn("лучины для плетения лаптей", phrases)
        self.assertIn("лучины для плетения корзин", phrases)


OLUT_HTML = (
    "<b>olu||t</b> <i>s</i> пиво; vägövä ~ крепкое пиво; panna ~tta варить пиво; "
    "varuštua id’üö ~oh приготовить солод на пиво; "
    "t’üt’öt pez’iečet’t’ih kävel’ijäl’l’ä ~olla девушки умывались бродящим пивом"
)


class CleanupRegressionGlossTestCase(_DictLabelTokensMixin, SimpleTestCase):
    """Gloss extraction regressions (not sanitize post-process)."""

    def test_olut_gloss_is_pivo_not_illustration(self):
        senses = gloss_senses_from_html(OLUT_HTML)
        joined = " | ".join(senses).lower()
        self.assertIn("пиво", joined)
        self.assertNotIn("крепкое пиво", joined)

    def test_bashka_naprimer_not_mangle_gloss(self):
        from translation_cleanup import _expand_comma_parallel

        self.assertEqual(
            _expand_comma_parallel("соленая голова крупной рыбы, например, сома"),
            "соленая голова крупной рыбы, например, сома",
        )
        html = (
            "<b>bašk||a</b> <i>s</i> соленая голова крупной рыбы, например, сома; "
            "pühäkši oššiin пример"
        )
        senses = gloss_senses_from_html(html)
        self.assertTrue(senses)
        self.assertFalse(any("крупной например" in s for s in senses))

    def test_expand_parallel_does_not_glue_through_parens(self):
        from translation_cleanup import _expand_comma_parallel

        self.assertEqual(
            _expand_comma_parallel("подниматься (о тесте), всходить"),
            "подниматься (о тесте), всходить",
        )
        self.assertEqual(
            _expand_comma_parallel("быть в обиде, печали"),
            "быть в обиде, быть в печали",
        )

    def test_ajua_shared_object_and_degot_expand(self):
        from translation_cleanup import _expand_comma_parallel

        self.assertEqual(
            _expand_comma_parallel("гнать смолу, деготь"),
            "гнать смолу, гнать деготь",
        )
        self.assertEqual(
            _expand_comma_parallel("вбить, вогнать гвоздь"),
            "вбить гвоздь, вогнать гвоздь",
        )
