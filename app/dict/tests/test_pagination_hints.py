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
    Characterization tests for the navigation hints.

    Each hint for page k is "first-of-page-k ·· first-of-page-(k+1)". The LAST
    page has no next page, so its range is closed with the very last word of
    the whole list ("šät ·· šöš"), UNLESS that would merely repeat the page's
    own start (single-word last page -> stays bare).

    SimpleTestCase (no DB): the helper is pure and only touches obj.word.
    Values verified against the function, not computed by hand.
    """

    def test_empty_returns_empty_dict(self):
        self.assertEqual({}, build_pagination_hints([], 18))

    def test_single_page_stays_bare(self):
        # One word == single-word last page: closing would repeat it -> bare.
        self.assertEqual({1: "aig"}, build_pagination_hints(_articles("aiga"), 18))

    def test_single_word_last_page_stays_bare(self):
        # per_page=1: every page is one word, so the last page's start equals
        # the last word -> the guard keeps it bare (no "muš ·· muš").
        self.assertEqual(
            {1: "aig ·· muš", 2: "muš"},
            build_pagination_hints(_articles("aiga", "muše"), 1),
        )

    def test_three_pages_distinct_prefixes(self):
        self.assertEqual(
            {1: "aig ·· akk", 2: "akk ·· muš", 3: "muš"},
            build_pagination_hints(_articles("aiga", "akka", "muše"), 1),
        )

    def test_extends_ngram_when_prefix_collides_with_neighbour(self):
        self.assertEqual(
            {1: "akk ·· akka", 2: "akka ·· muš", 3: "muš"},
            build_pagination_hints(_articles("akku", "akka", "muše"), 1),
        )

    def test_uses_normalized_karelian_form(self):
        self.assertEqual(
            {1: "tuu ·· tuut", 2: "tuut ·· muš", 3: "muš"},
            build_pagination_hints(_articles("tuwl’i", "tuwta", "muše"), 1),
        )

    def test_inner_word_shorter_than_three_keeps_initial_ngram(self):
        self.assertEqual(
            {1: "aig ·· yö", 2: "yö ·· muš", 3: "muš"},
            build_pagination_hints(_articles("aiga", "yö", "muše"), 1),
        )

    def test_last_page_range_is_closed_with_last_word(self):
        # Multi-word last page [šät, šäx, šöš]: first-of-page 'šät' differs from
        # the last word 'šöš', so the final hint closes the range -> "šät ·· šöš".
        # 6 words, per_page=3 -> pages [šab,šag,šei] and [šät,šäx,šöš].
        self.assertEqual(
            {1: "šab ·· šät", 2: "šät ·· šöš"},
            build_pagination_hints(
                _articles("šab", "šag", "šei", "šät", "šäx", "šöš"), 3
            ),
        )

    def test_realistic_per_page_slice_closes_last_range(self):
        # per_page=18 over 40 items -> first words at 0, 18, 36; last word at 39.
        # Last page's start ('yot') differs from the last word -> range closed.
        words = [f"w{i:02d}word" for i in range(40)]
        words[0] = "aigateksti"
        words[18] = "muanteksti"
        words[36] = "yoteksti"
        self.assertEqual(
            {1: "aig ·· mua", 2: "mua ·· yot", 3: "yot ·· u39"},
            build_pagination_hints(_articles(*words), 18),
        )
