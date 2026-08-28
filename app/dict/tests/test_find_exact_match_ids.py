from django.test import SimpleTestCase

from ..search import find_exact_match_ids


class FindExactMatchIdsTestCase(SimpleTestCase):
    """
    Exact matches for ?f=exact, pure/no DB:
      * ILIKE hit on rus_word == query within result_ids;
      * inherited: translationless article linked (1 hop) to such a hit.
    Signature: find_exact_match_ids(result_ids, ilike_ids, blobs_by_article, links).
    """

    def test_ilike_hit_in_result(self):
        self.assertEqual(
            {1},
            find_exact_match_ids({1, 2}, {1}, {1: ["быстро", "круто"]}, {}),
        )

    def test_phrase_only_not_exact_without_ilike(self):
        # ehatta: only «быстро ехать» — in выдача via FTS, not exact for «быстро».
        self.assertEqual(
            set(),
            find_exact_match_ids({2}, set(), {2: ["быстро ехать"]}, {}),
        )

    def test_mixed_ilike_and_phrase(self):
        self.assertEqual(
            {1, 3},
            find_exact_match_ids(
                {1, 2, 3},
                {1, 3},
                {1: ["быстро"], 2: ["быстро ехать"], 3: ["быстро", "быстро пробежать"]},
                {},
            ),
        )

    def test_translationless_inherits_from_ilike_neighbor(self):
        self.assertEqual(
            {1, 3},
            find_exact_match_ids(
                {1, 3},
                {1},
                {1: ["быстро"]},
                {3: {1}, 1: {3}},
            ),
        )

    def test_translationless_does_not_inherit_from_phrase_only_neighbor(self):
        self.assertEqual(
            set(),
            find_exact_match_ids(
                {2, 3},
                set(),
                {2: ["быстро ехать"]},
                {3: {2}, 2: {3}},
            ),
        )

    def test_linked_with_own_translations_excluded_without_ilike(self):
        # Linked to ruttoh but own translations don't match query.
        self.assertEqual(
            {1},
            find_exact_match_ids(
                {1, 4},
                {1},
                {1: ["быстро"], 4: ["медленно", "торопиться"]},
                {4: {1}, 1: {4}},
            ),
        )

    def test_ilike_outside_result_ignored(self):
        self.assertEqual(
            set(),
            find_exact_match_ids({2}, {1}, {2: ["медленно"]}, {}),
        )
