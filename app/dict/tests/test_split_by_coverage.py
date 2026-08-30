from django.test import SimpleTestCase

from ..search import STOPWORDS, split_by_coverage

STOPS = STOPWORDS
QW = {"быстро"}  # query_words for the anchor "быстро"


class SplitByCoverageTestCase(SimpleTestCase):
    """
    Characterization tests for the narrowing split (SPEC v2). Pure, no DB.

    candidate -> LABEL (query words removed by EXACT match, stop-words kept)
    -> KEY (stop-words removed). coverage = cards whose blob contains any key
    token. 0 < c < N -> narrowing; c in {0, N} or empty key -> dropped.

    No "similar" class: candidates are the anchor's own full-text hits, so a
    jump-out (coverage 0) is unreachable here (SPEC v2 §0, §2). Only EXACT
    query words are stripped; morphological variants leak (see last test).
    Values verified against the function, not computed by hand.
    """

    def test_empty_key_dropped(self):
        # "быстро" is a query word -> stripped -> empty key. "быстрее" is a
        # variant that survives, but its key covers no blob here -> dropped.
        self.assertEqual(
            [], split_by_coverage(["быстро", "быстрее"], ["быстро говорить"], QW, STOPS)
        )

    def test_single_narrowing(self):
        self.assertEqual(
            [{"label": "говорить", "key": "говорить", "coverage": 1}],
            split_by_coverage(
                ["быстро говорить"], ["быстро говорить", "быстро ехать"], QW, STOPS
            ),
        )

    def test_coverage_zero_dropped(self):
        # Key "вершине" appears on no card -> dropped (not a "similar"; jumps
        # out are a separate mechanism, SPEC v2).
        self.assertEqual(
            [],
            split_by_coverage(
                ["быстро к вершине"], ["быстро говорить", "быстро ехать"], QW, STOPS
            ),
        )

    def test_coverage_full_dropped(self):
        self.assertEqual(
            [],
            split_by_coverage(
                ["быстро делать"], ["говорить делать", "ехать делать"], QW, STOPS
            ),
        )

    def test_dedup_by_key_first_label_wins(self):
        self.assertEqual(
            [{"label": "говорить", "key": "говорить", "coverage": 1}],
            split_by_coverage(
                ["быстро говорить", "говорить быстро"],
                ["быстро говорить", "быстро ехать"],
                QW,
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
                QW,
                STOPS,
            ),
        )

    def test_label_keeps_stopword_key_drops_it(self):
        self.assertEqual(
            [{"label": "на лошади", "key": "лошади", "coverage": 1}],
            split_by_coverage(
                ["быстро на лошади"],
                ["быстро ехать лошади", "быстро говорить"],
                QW,
                STOPS,
            ),
        )

    def test_multitoken_key_matches_any_token(self):
        self.assertEqual(
            [{"label": "ехать лошади", "key": "ехать лошади", "coverage": 2}],
            split_by_coverage(
                ["быстро ехать лошади"],
                ["быстро ехать", "конь лошади", "прыгать"],
                QW,
                STOPS,
            ),
        )

    def test_label_keeps_parens_from_original_phrase(self):
        self.assertEqual(
            [
                {
                    "label": "первотельная (о корове)",
                    "key": "первотельная корове",
                    "coverage": 1,
                }
            ],
            split_by_coverage(
                ["первотельная (о корове)"],
                ["первотельная (о корове)", "дойная корова"],
                {"корова"},
                STOPS,
            ),
        )

    def test_query_form_variant_leaks_into_label(self):
        # Accepted limitation (SPEC v2, deferred): only EXACT query words are
        # removed. A morphological variant of the query ("быстрее" vs query
        # "быстро") is NOT stripped and leaks into label and key.
        self.assertEqual(
            [{"label": "быстрее в движении", "key": "быстрее движении", "coverage": 1}],
            split_by_coverage(
                ["быстрее в движении"], ["стало быстрее", "медленно"], QW, STOPS
            ),
        )
