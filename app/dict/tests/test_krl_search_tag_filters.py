from django.test import Client, TestCase

from ..models import Article, ArticleIndexTag, Tag
from ..search import (
    format_krl_filter_query,
    format_krl_t_query,
    krl_tag_facets,
    normalize_krl_tag_ids,
    num_by_page,
    parse_krl_phrase_param,
    parse_krl_tag_param,
    word_search,
)


class ParseNormalizeKrlTagParamTestCase(TestCase):
    def setUp(self):
        self.adj = Tag.objects.create(
            tag="a", name="adjectivum", type=2, sorting=1, level=0
        )
        self.comp = Tag.objects.create(
            tag="comp", name="comparativus", type=2, sorting=2, level=1
        )
        self.noun = Tag.objects.create(
            tag="s", name="substantivum", type=2, sorting=3, level=0
        )
        self.geo = Tag.objects.create(tag="g1", name="Гео 1", type=1, sorting=1)
        self.style = Tag.objects.create(tag="st", name="перен.", type=3, sorting=1)
        self.phr = Tag.objects.create(tag="phr", name="фразеологизм", type=5, sorting=1)

    def test_parse_empty(self):
        self.assertEqual(parse_krl_tag_param(None), [])
        self.assertEqual(parse_krl_tag_param(""), [])
        self.assertEqual(parse_krl_tag_param(" , "), [])

    def test_parse_mixed_junk(self):
        self.assertEqual(
            parse_krl_tag_param("12,x,34,"),
            [12, 34],
        )

    def test_parse_phrase_param(self):
        self.assertTrue(parse_krl_phrase_param("1"))
        self.assertTrue(parse_krl_phrase_param("yes"))
        self.assertFalse(parse_krl_phrase_param(None))
        self.assertFalse(parse_krl_phrase_param("0"))

    def test_normalize_one_per_type_and_drop_child(self):
        ids = normalize_krl_tag_ids(
            [
                self.comp.id,
                self.adj.id,
                self.noun.id,
                self.geo.id,
                self.style.id,
                self.phr.id,
            ]
        )
        # child + type5 dropped; second type=2 kept only first parent in input order
        self.assertEqual(ids, [self.adj.id, self.style.id, self.geo.id])

    def test_format_query(self):
        self.assertEqual(format_krl_t_query([]), "")
        self.assertEqual(format_krl_t_query([1, 2]), "?t=1,2")
        self.assertEqual(format_krl_filter_query([], phrase=True), "?ph=1")
        self.assertEqual(format_krl_filter_query([1], phrase=True), "?t=1&ph=1")


class KrlSearchTagFiltersTestCase(TestCase):
    def setUp(self):
        self.adj = Tag.objects.create(
            tag="a", name="adjectivum", type=2, sorting=1, level=0
        )
        self.comp = Tag.objects.create(
            tag="comp", name="comparativus", type=2, sorting=2, level=1
        )
        self.noun = Tag.objects.create(
            tag="s", name="substantivum", type=2, sorting=3, level=0
        )
        self.geo1 = Tag.objects.create(tag="g1", name="Гео 1", type=1, sorting=1)
        self.geo2 = Tag.objects.create(tag="g2", name="Гео 2", type=1, sorting=2)
        self.phr = Tag.objects.create(tag="phr", name="фразеологизм", type=5, sorting=1)

        # Shared stem; public KRL search needs ?/% for prefix (exact ILIKE otherwise)
        self.a_adj = self._article("kaaa", [self.adj])
        self.a_noun = self._article("kaab", [self.noun])
        self.a_both = self._article("kaac", [self.adj, self.geo1])
        self.a_geo2 = self._article("kaad", [self.noun, self.geo2])
        self.a_child_only = self._article("kaae", [self.comp])
        self.a_phr = self._article("kaaf", [self.adj, self.phr])
        self.q = "kaa?"

    def _article(self, word, tags):
        art = Article.objects.create(word=word)
        for tag in tags:
            ArticleIndexTag.objects.create(article=art, tag=tag)
        return art

    def _words(self, page_obj):
        return {a.word for a in page_obj.object_list}

    def test_filter_and_between_groups(self):
        page_obj, count, groups, phrase, t_query = word_search(
            self.q, 1, [self.adj.id, self.geo1.id]
        )
        self.assertEqual(count, 1)
        self.assertEqual(self._words(page_obj), {"kaac"})
        self.assertEqual(t_query, "?t=%s,%s" % (self.adj.id, self.geo1.id))
        self.assertIsNone(phrase)

    def test_one_tag_per_type(self):
        page_obj, count, _, _, _ = word_search(self.q, 1, [self.adj.id, self.noun.id])
        # only first type=2 kept -> adjectivum articles
        self.assertEqual(self._words(page_obj), {"kaaa", "kaac", "kaaf"})
        self.assertEqual(count, 3)

    def test_phrase_filter(self):
        page_obj, count, groups, phrase, t_query = word_search(self.q, 1, phrase=True)
        self.assertEqual(self._words(page_obj), {"kaaf"})
        self.assertEqual(count, 1)
        self.assertEqual(t_query, "?ph=1")
        self.assertTrue(phrase["checked"])
        self.assertIn("фразеологизмами", phrase["label"])

    def test_phrase_and_tag_and(self):
        page_obj, count, _, _, t_query = word_search(
            self.q, 1, [self.adj.id], phrase=True
        )
        self.assertEqual(self._words(page_obj), {"kaaf"})
        self.assertEqual(t_query, "?t=%s&ph=1" % self.adj.id)

    def test_grammar_child_excluded_from_facets(self):
        groups, phrase = krl_tag_facets(
            {self.a_adj.id, self.a_noun.id, self.a_child_only.id}, []
        )
        gram = next(g for g in groups if g["type"] == 2)
        labels = {o["label"] for o in gram["options"]}
        self.assertIn("adjectivum", labels)
        self.assertIn("substantivum", labels)
        self.assertNotIn("comparativus", labels)
        self.assertIsNone(phrase)

    def test_phrase_checkbox_when_diverse(self):
        groups, phrase = krl_tag_facets(
            {self.a_adj.id, self.a_phr.id, self.a_noun.id}, []
        )
        self.assertIsNotNone(phrase)
        self.assertFalse(phrase["checked"])
        ph_group = next(g for g in groups if g["type"] == "ph")
        self.assertIsNone(ph_group["title"])
        self.assertEqual(
            [o["label"] for o in ph_group["options"]],
            ["словарные статьи с фразеологизмами"],
        )
        # sits after grammar when no stylistic group
        types = [g["type"] for g in groups]
        self.assertIn("ph", types)
        self.assertEqual(types.index("ph"), types.index(2) + 1)

    def test_active_chip_toggles_off(self):
        groups, _ = krl_tag_facets(
            {self.a_adj.id, self.a_noun.id, self.a_both.id},
            [self.adj.id],
        )
        gram = next(g for g in groups if g["type"] == 2)
        # Selected group shows only the active chip (siblings hidden).
        self.assertEqual(len(gram["options"]), 1)
        opt = gram["options"][0]
        self.assertEqual(opt["id"], self.adj.id)
        self.assertTrue(opt["selected"])
        self.assertEqual(opt["t_query"], "")

    def test_selected_group_stays_visible_when_narrowed(self):
        # folklor-like style + grammar: after picking grammar, style group would
        # have <2 options in the facet — still show the selected style chip alone.
        style1 = Tag.objects.create(tag="folk", name="фольклор", type=3, sorting=1)
        style2 = Tag.objects.create(tag="pern", name="перен.", type=3, sorting=2)
        a_folk_adj = self._article("kaafolk", [style1, self.adj])
        a_pern_noun = self._article("kaapern", [style2, self.noun])
        a_folk_only = self._article("kaafonly", [style1])
        base = {
            a_folk_adj.id,
            a_pern_noun.id,
            a_folk_only.id,
            self.a_adj.id,
            self.a_noun.id,
        }
        # Both styles available without selection
        groups0, _ = krl_tag_facets(base, [])
        style_g0 = next(g for g in groups0 if g["type"] == 3)
        self.assertGreaterEqual(len(style_g0["options"]), 2)

        # folklor then adjectivum — style group must still show folklor only
        groups, _ = krl_tag_facets(base, [style1.id, self.adj.id])
        style_g = next(g for g in groups if g["type"] == 3)
        self.assertEqual([o["id"] for o in style_g["options"]], [style1.id])
        self.assertTrue(style_g["options"][0]["selected"])
        # clearing style keeps grammar
        self.assertEqual(
            style_g["options"][0]["t_query"],
            "?t=%s" % self.adj.id,
        )
        gram = next(g for g in groups if g["type"] == 2)
        self.assertEqual([o["id"] for o in gram["options"]], [self.adj.id])

    def test_hide_uniform_group(self):
        # grammar varies (adj+noun); geo only geo1 -> hide geo group
        groups, _ = krl_tag_facets({self.a_both.id, self.a_adj.id, self.a_noun.id}, [])
        types = {g["type"] for g in groups}
        self.assertNotIn(1, types)
        self.assertIn(2, types)

    def test_hide_block_when_narrow_single_page_single_tag(self):
        groups, phrase = krl_tag_facets({self.a_adj.id}, [])
        self.assertEqual(groups, [])
        self.assertIsNone(phrase)

    def test_show_block_when_multi_page_even_if_building_facets(self):
        # many articles, two grammar parents -> group visible
        arts = []
        for i in range(num_by_page + 2):
            arts.append(
                self._article("kaax%02d" % i, [self.adj if i % 2 else self.noun])
            )
        base = {a.id for a in arts}
        groups, _ = krl_tag_facets(base, [])
        self.assertTrue(any(g["type"] == 2 for g in groups))

    def test_view_preserves_t_in_pagination_link(self):
        client = Client()
        # pad to >1 page
        for i in range(num_by_page + 1):
            self._article("kaap%02d" % i, [self.adj if i < 5 else self.noun])
        resp = client.get("/search/kaa%3F/1", {"t": str(self.adj.id)})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="krlTagFilters"')
        self.assertContains(resp, "?t=%s" % self.adj.id)

    def test_view_phrase_checkbox(self):
        client = Client()
        resp = client.get("/search/kaa%3F/1", {"ph": "1"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "словарные статьи с фразеологизмами")
        self.assertContains(resp, "kaaf")
        html = resp.content.decode()
        self.assertRegex(
            html,
            r"krl-tag-opt is-active[^>]*>\s*словарные статьи с фразеологизмами\s*&times;",
        )

    def test_russian_search_unaffected(self):
        client = Client()
        resp = client.get("/search/%D0%BA%D0%BE%D1%88%D0%BA%D0%B0/1")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'id="krlTagFilters"')
