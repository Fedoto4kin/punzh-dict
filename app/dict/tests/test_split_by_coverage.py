from django.test import SimpleTestCase

from ..search import split_by_coverage

STOPS = {"к", "на", "и", "с", "в", "что-л"}
STEM = "быстр"


class SplitByCoverageTestCase(SimpleTestCase):
    """
    Characterization tests for the narrowing split (SPEC v2). Pure, no DB:
    anchor stem and stop-words are parameters, so no corpus is needed.

    candidate -> LABEL (anchor removed, stop-words kept) -> KEY (stop-words
    removed). coverage = cards whose translation blob contains any key token.
      0 < c < N -> narrowing tag; c == 0, c == N, or empty key -> dropped.

    There is no "similar" class: candidates come from the anchor's own
    full-text hits, so a jump-out (coverage 0) is structurally unreachable
    here; it is served by a separate mechanism (SPEC v2 §0, §2). Values
    verified against the function, not computed by hand.
    """

    def test_empty_key_dropped(self):
        # The anchor itself and its inflections leave no key -> dropped.
        self.assertEqual(
            [], split_by_coverage(["быстро", "быстрее"], ["быстро говорить"], STEM, STOPS)
        )

    def test_single_narrowing(self):
        self.assertEqual(
            [{"label": "говорить", "key": "говорить", "coverage": 1}],
            split_by_coverage(
                ["быстро говорить"], ["быстро говорить", "быстро ехать"], STEM, STOPS
            ),
        )

    def test_coverage_zero_dropped(self):
        # Key "вершине" appears on no card. Under SPEC v2 this is NOT a similar
        # query — it is simply dropped (jumps out are a separate mechanism).
        self.assertEqual(
            [],
            split_by_coverage(
                ["быстро к вершине"], ["быстро говорить", "быстро ехать"], STEM, STOPS
            ),
        )

    def test_coverage_full_dropped(self):
        # Key present on every card -> synonym of the anchor -> dropped.
        self.assertEqual(
            [],
            split_by_coverage(
                ["быстро делать"], ["говорить делать", "ехать делать"], STEM, STOPS
            ),
        )

    def test_dedup_by_key_first_label_wins(self):
        self.assertEqual(
            [{"label": "говорить", "key": "говорить", "coverage": 1}],
            split_by_coverage(
                ["быстро говорить", "говорить быстро"],
                ["быстро говорить", "быстро ехать"],
                STEM,
                STOPS,
            ),
        )

    def test_sorted_by_ascending_coverage(self):
        self.assertEqual(
            [
                {"label": "ехать", "key": "ехать", "coverage": 1},
                {"label": "говорить", "key": "говорить", "coverage": 2},
            ],
            split_by_coverage(
                ["быстро говорить", "быстро ехать"],
                [
                    "быстро говорить",
                    "быстро говорить невнятно",
                    "быстро ехать",
                    "быстро жевать",
                ],
                STEM,
                STOPS,
            ),
        )

    def test_label_keeps_stopword_key_drops_it(self):
        # LABEL "на лошади" (shown), KEY "лошади" (matched). Distinct on purpose.
        self.assertEqual(
            [{"label": "на лошади", "key": "лошади", "coverage": 1}],
            split_by_coverage(
                ["быстро на лошади"],
                ["быстро ехать лошади", "быстро говорить"],
                STEM,
                STOPS,
            ),
        )

    def test_multitoken_key_matches_any_token(self):
        # Multi-token key covers a card if ANY token is a substring.
        self.assertEqual(
            [{"label": "ехать лошади", "key": "ехать лошади", "coverage": 2}],
            split_by_coverage(
                ["быстро ехать лошади"],
                ["быстро ехать", "конь лошади", "прыгать"],
                STEM,
                STOPS,
            ),
        )
