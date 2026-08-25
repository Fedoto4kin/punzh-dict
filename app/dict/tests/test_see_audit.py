from types import SimpleNamespace

from django.test import SimpleTestCase

from dict.see_audit import (
    article_headword_keys,
    classify_html,
    html_see_lemmas,
    html_see_mentions,
    is_see_marker,
    link_see_lemmas,
    marker_issues,
    propose_html_fix,
)


class SeeAuditTest(SimpleTestCase):
    def test_canon_see(self):
        c = classify_html("<i>см.</i> ruttoh; foo")
        self.assertEqual(len(c["canon"]), 1)
        self.assertEqual(c["canon"][0]["lemma"], "ruttoh")
        self.assertFalse(c["no_period"])
        self.assertFalse(c["bare"])

    def test_no_period_italic(self):
        self.assertIn("no_period", marker_issues("см"))
        c = classify_html("<i>см</i> marawttua")
        self.assertTrue(c["no_period"])
        self.assertFalse(c["canon"])

    def test_latin_c_in_italic(self):
        inner = "cм."  # latin c + cyrillic м
        self.assertTrue(is_see_marker(inner))
        self.assertIn("mixed_script", marker_issues(inner))

    def test_bare_see_before_latin(self):
        c = classify_html("лексема см. mägrä.")
        self.assertTrue(c["bare"])
        self.assertEqual(c["bare"][0]["lemma"], "mägrä")

    def test_smeh_not_bare(self):
        c = classify_html("громкий смех в избе")
        self.assertFalse(c["bare"])
        self.assertFalse(c["canon"])

    def test_comma_list(self):
        c = classify_html("<i>ср.</i> koinpid’äja, kod’ikaš")
        self.assertEqual(len(c["comma_list"]), 1)
        self.assertEqual(c["comma_list"][0]["lemmas"], ["koinpid’äja", "kod’ikaš"])

    def test_deriv_tagged(self):
        html = "<b>marawt||ella</b> <i>v</i> <i>freq</i> от marawttua; kanat"
        c = classify_html(html)
        self.assertEqual(c["deriv_tagged"][0]["lemma"], "marawttua")
        self.assertFalse(c["deriv_loose"])

    def test_propose_bare_see(self):
        html = propose_html_fix("лексема см. baba; foo")
        self.assertIn("<i>см.</i> baba", html)
        self.assertFalse(classify_html(html)["bare"])

    def test_propose_period_outside_italic(self):
        html = propose_html_fix("гармонь; <i>ср</i>. šoittu")
        self.assertIn("<i>ср.</i> šoittu", html)
        self.assertFalse(classify_html(html)["no_period"])

    def test_propose_latin_p(self):
        html = propose_html_fix("cp. röhkiä; сp. ruga")
        self.assertIn("<i>ср.</i> röhkiä", html)
        self.assertIn("<i>ср.</i> ruga", html)

    def test_propose_see_without_period(self):
        html = propose_html_fix("см rud’juo")
        self.assertIn("<i>см.</i> rud’juo", html)

    def test_propose_idempotent_canon(self):
        src = "<i>см.</i> abie; <i>ср.</i> abevus"
        self.assertEqual(propose_html_fix(src), src)

    def test_link_single_lemma(self):
        html = link_see_lemmas("<i>см.</i> ruttoh; foo")
        self.assertIn('<a href="/search/ruttoh">ruttoh</a>', html)
        self.assertIn("foo", html)
        self.assertNotIn('href="/search/foo"', html)

    def test_semicolon_does_not_eat_illustration(self):
        cases = [
            (
                "<b>ad’vo</b> <i>s</i> <i>см.</i> ad’ivo; istuw kun ~, ei kehtua ruadua",
                "ad’ivo",
                "istuw",
            ),
            (
                "<b>abevu||s</b> <i>s</i> <i>см.</i> abie 1; vierahalla rannalla pid’i t’irpi̮a ~tta",
                "abie",
                "vierahalla",
            ),
            (
                "<b>ähät’ä</b> <i>v</i> <i>см.</i> ähkät’ä; ollet keriät randah",
                "ähkät’ä",
                "ollet",
            ),
            (
                "<b>kopakkah</b> <i>adv</i> <i>см.</i> kopakašti; "
                "har’jatešša i kuduos’s’a karbiet pöl’is’s’äh",
                "kopakašti",
                "har’jatešša",
            ),
        ]
        for src, lemma, illus in cases:
            with self.subTest(lemma=lemma):
                self.assertEqual(html_see_lemmas(src), [lemma])
                self.assertFalse(classify_html(src)["comma_list"])
                html = link_see_lemmas(src)
                self.assertIn(f'<a href="/search/{lemma}">{lemma}</a>', html)
                self.assertNotIn(f'href="/search/{illus}"', html)
                self.assertIn(illus, html)

    def test_semicolon_illustration_starting_with_v(self):
        src = (
            "<b>bat’inka</b> <i>s</i> <i>см.</i> bot’inka; "
            "jallašša voijettu gutal’inalla ~t"
        )
        self.assertEqual(html_see_lemmas(src), ["bot’inka"])
        html = link_see_lemmas(src)
        self.assertIn('<a href="/search/bot’inka">bot’inka</a>', html)
        self.assertNotIn("jallašša</a>", html)

    def test_link_comma_list(self):
        html = link_see_lemmas("<i>ср.</i> koinpid’äja, kod’ikaš")
        self.assertIn('<a href="/search/koinpid’äja">koinpid’äja</a>', html)
        self.assertIn('<a href="/search/kod’ikaš">kod’ikaš</a>', html)
        self.assertIn(", ", html)

    def test_html_see_mentions(self):
        html = "<i>см.</i> ruttoh; foo"
        self.assertTrue(html_see_mentions(html, ["ruttoh", "rutto||h"]))
        self.assertFalse(html_see_mentions(html, ["abie"]))
        self.assertFalse(html_see_mentions("<i>freq</i> от marawttua", ["marawttua"]))

    def test_mentions_folds_pipes_and_apostrophes(self):
        html = "<i>см.</i> ehät’t’iä"
        self.assertTrue(html_see_mentions(html, ["ehät’||t’iä", "ehättiä"]))
        self.assertTrue(html_see_mentions(html, ["ehät’t’iä"]))

    def test_headword_keys_glue_double_pipe_not_compound_tail(self):
        simple = SimpleNamespace(word="riw||gu, ~gun’e", word_normalized=None)
        compound = SimpleNamespace(word="humala|riwgu", word_normalized=None)
        keys = article_headword_keys(simple)
        self.assertIn("riwgu", keys)
        self.assertIn("riugu", keys)
        self.assertNotIn("riwgu", article_headword_keys(compound))
        self.assertIn("humalariwgu", article_headword_keys(compound))

    def test_fold_strips_homonym_and_diacritics(self):
        from dict.see_audit import fold_lemma

        self.assertEqual(fold_lemma("čašk||a I"), "caska")
        self.assertEqual(fold_lemma("muč||čo, ~čon’e"), "mucco")
        self.assertEqual(fold_lemma("čaška"), "caska")
        self.assertEqual(fold_lemma("muččo"), "mucco")

    def test_mentions_matches_index_style_forms(self):
        html = "<i>см.</i> čaška; foo"
        self.assertTrue(html_see_mentions(html, ["čašk||a I", "caska"]))
        self.assertTrue(
            html_see_mentions("<i>ср.</i> muččo 1", ["muč||čo, ~čon’e", "mucco"])
        )

    def test_comma_list_skips_homonym_numbers(self):
        c = classify_html("<i>см.</i> mado 2, šano 1")
        self.assertEqual(c["comma_list"][0]["lemmas"], ["mado", "šano"])

    def test_link_skips_homonym_numbers(self):
        html = link_see_lemmas("<i>см.</i> mado 2, šano 1;")
        self.assertIn('<a href="/search/mado">mado</a> 2', html)
        self.assertIn('<a href="/search/šano">šano</a> 1', html)
        self.assertNotIn('href="/search/2"', html)
        self.assertNotIn(">2</a>", html)

    def test_semicolon_list_with_roman_and_arabic(self):
        src = "<i>ср.</i> kappa I 2; n’el’l’ikkö 1;"
        c = classify_html(src)
        self.assertEqual(c["comma_list"][0]["lemmas"], ["kappa", "n’el’l’ikkö"])
        html = link_see_lemmas(src)
        self.assertIn('<a href="/search/kappa">kappa</a> I 2', html)
        self.assertIn('<a href="/search/n’el’l’ikkö">n’el’l’ikkö</a> 1', html)
        self.assertIn("; ", html)
        self.assertTrue(html.rstrip().endswith(";"))
        self.assertNotIn('href="/search/I"', html)
        self.assertNotIn('href="/search/2"', html)
