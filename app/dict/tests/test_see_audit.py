from django.test import SimpleTestCase

from dict.see_audit import (
    classify_html,
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
