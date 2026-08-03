from django.test import SimpleTestCase

from ..search import find_direct_hits


class FindDirectHitsTestCase(SimpleTestCase):
    """
    Direct hits (SPEC v2), pure/no DB. Two ways to qualify:
      * base: every rus_word entry is a single token (ruttoh);
      * inherited: no translations of its own, but linked (either direction)
        to a BASE direct hit (rutoldi -> "см. ruttoh"), one hop only.
    Signature: find_direct_hits(blobs_by_article, result_ids, links),
    links = {article_id: set(neighbour_ids)}. Values verified against fn.
    """

    def test_all_single_word_is_direct(self):
        self.assertEqual(
            {1}, find_direct_hits({1: ["быстро", "круто", "скоро"]}, {1}, {})
        )

    def test_any_phrase_is_not_direct(self):
        self.assertEqual(set(), find_direct_hits({2: ["быстро пробежать"]}, {2}, {}))

    def test_translationless_orphan_is_not_direct(self):
        # No translations and no links -> nothing to inherit from.
        self.assertEqual(set(), find_direct_hits({}, {3}, {}))

    def test_translationless_inherits_from_linked_direct(self):
        # rutoldi (3): no translations, linked to base-direct ruttoh (1).
        self.assertEqual(
            {1, 3},
            find_direct_hits({1: ["быстро"]}, {1, 3}, {3: {1}, 1: {3}}),
        )

    def test_translationless_does_not_inherit_from_phrase(self):
        # Linked only to a phrase (non-direct) article -> not inherited.
        self.assertEqual(
            set(),
            find_direct_hits({2: ["быстро пробежать"]}, {2, 3}, {3: {2}, 2: {3}}),
        )

    def test_mixed(self):
        self.assertEqual(
            {1, 4},
            find_direct_hits(
                {1: ["быстро"], 2: ["быстро пробежать"]},
                {1, 2, 4, 5},
                {4: {1}, 1: {4}},
            ),
        )

    def test_empty_translation_list_is_not_direct(self):
        self.assertEqual(set(), find_direct_hits({5: []}, {5}, {}))

    def test_single_token_pometa_counts_as_direct(self):
        # "что-л." is one token -> single -> direct. Data quirk, accepted.
        self.assertEqual({6}, find_direct_hits({6: ["что-л."]}, {6}, {}))
