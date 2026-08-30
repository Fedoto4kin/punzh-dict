from django.test import SimpleTestCase

from ..search import STOPWORDS, split_by_coverage

STOPS = STOPWORDS
QW = {"быстро"}  # query_words for the anchor "быстро"


class SplitByCoverageTestCase(SimpleTestCase):
    """
    Characterization tests for the narrowing split (SPEC v2). Pure, no DB.

    candidate -> LABEL (full phrase) -> KEY (query words and stop-words removed).
    coverage = cards whose blob contains any key token. 0 < c < N -> narrowing.
    """

    def test_empty_key_dropped(self):
        self.assertEqual(
            [], split_by_coverage(["быстро", "быстрее"], ["быстро говорить"], QW, STOPS)
        )

    def test_single_narrowing(self):
        self.assertEqual(
            [{"label": "быстро говорить", "key": "говорить", "coverage": 1}],
            split_by_coverage(
                ["быстро говорить"], ["быстро говорить", "быстро ехать"], QW, STOPS
            ),
        )

    def test_coverage_zero_dropped(self):
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
            [{"label": "быстро говорить", "key": "говорить", "coverage": 1}],
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
                {"label": "быстро ехать", "key": "ехать", "coverage": 1},
                {"label": "быстро говорить", "key": "говорить", "coverage": 2},
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

    def test_label_shows_full_phrase_key_drops_stopwords(self):
        self.assertEqual(
            [{"label": "быстро на лошади", "key": "лошади", "coverage": 1}],
            split_by_coverage(
                ["быстро на лошади"],
                ["быстро ехать лошади", "быстро говорить"],
                QW,
                STOPS,
            ),
        )

    def test_multitoken_key_matches_any_token(self):
        self.assertEqual(
            [
                {
                    "label": "быстро ехать лошади",
                    "key": "ехать лошади",
                    "coverage": 2,
                }
            ],
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

    def test_query_form_variant_in_full_label_and_key(self):
        self.assertEqual(
            [
                {
                    "label": "быстрее в движении",
                    "key": "быстрее движении",
                    "coverage": 1,
                }
            ],
            split_by_coverage(
                ["быстрее в движении"], ["стало быстрее", "медленно"], QW, STOPS
            ),
        )
