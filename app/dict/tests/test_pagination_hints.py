from django.test import SimpleTestCase

from ..helpers import build_pagination_hints


class _Stub:
    """Minimal stand-in for Article: build_pagination_hints only reads .word."""

    def __init__(self, word):
        self.word = word


def _articles(*words):
    return [_Stub(w) for w in words]


class BuildPaginationHintsTestCase(SimpleTestCase):
    """
    Characterization tests: they pin the CURRENT behaviour of the helper
    extracted from search_by_pointer / search_by_tags_smart, so that the
    upcoming sort_and_paginate refactor cannot change it silently.

    SimpleTestCase (no DB): the helper is pure and only touches obj.word.
    Expected values were captured by running the real function against
    create_ngram / normalization, not computed by hand.
    """

    def test_empty_returns_empty_dict(self):
        # No pages -> empty mapping (not None). Both endpoints of search.py
        # now rely on {} here.
        self.assertEqual({}, build_pagination_hints([], 18))

    def test_single_page(self):
        # One first-word: just its 3-gram, no " ·· " suffix.
        self.assertEqual({1: "aig"}, build_pagination_hints(_articles("aiga"), 18))

    def test_two_pages_endpoints_only(self):
        # Two first-words -> no inner boundary to disambiguate; the first
        # hint is joined with the next, the last keeps no suffix.
        self.assertEqual(
            {1: "aig ·· muš", 2: "muš"},
            build_pagination_hints(_articles("aiga", "muše"), 1),
        )

    def test_three_pages_distinct_prefixes(self):
        # Distinct 3-grams: no extension needed, n stays at 3.
        self.assertEqual(
            {1: "aig ·· akk", 2: "akk ·· muš", 3: "muš"},
            build_pagination_hints(_articles("aiga", "akka", "muše"), 1),
        )

    def test_extends_ngram_when_prefix_collides_with_neighbour(self):
        # Inner word 'akka' shares 'akk' with the previous 'akku', so the
        # loop extends n from 3 to 4 to make the hint unambiguous ('akka').
        self.assertEqual(
            {1: "akk ·· akka", 2: "akka ·· muš", 3: "muš"},
            build_pagination_hints(_articles("akku", "akka", "muše"), 1),
        )

    def test_uses_normalized_karelian_form(self):
        # Hints are built from the NORMALIZED word: 'w' -> 'u', palatal ' dropped.
        # 'tuwl'i'/'tuwta' collide at 'tuu' and extend to 'tuut'.
        self.assertEqual(
            {1: "tuu ·· tuut", 2: "tuut ·· muš", 3: "muš"},
            build_pagination_hints(_articles("tuwl’i", "tuwta", "muše"), 1),
        )

    def test_inner_word_shorter_than_three_keeps_initial_ngram(self):
        # Subtle inherited behaviour: the while-loop bound uses the RAW .word
        # length while create_ngram works on the normalized form. For the inner
        # 'yö' (raw len 2) the disambiguation body is skipped and the initial
        # 3-gram is kept as-is. Pinned deliberately, not endorsed.
        self.assertEqual(
            {1: "aig ·· yö", 2: "yö ·· muš", 3: "muš"},
            build_pagination_hints(_articles("aiga", "yö", "muše"), 1),
        )

    def test_realistic_per_page_slice(self):
        # per_page=18 over 40 items -> first words at indices 0, 18, 36.
        words = [f"w{i:02d}word" for i in range(40)]
        words[0] = "aigateksti"
        words[18] = "muanteksti"
        words[36] = "yoteksti"
        self.assertEqual(
            {1: "aig ·· mua", 2: "mua ·· yot", 3: "yot"},
            build_pagination_hints(_articles(*words), 18),
        )
