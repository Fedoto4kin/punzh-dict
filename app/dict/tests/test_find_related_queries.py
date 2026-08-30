from django.test import SimpleTestCase

from ..search import find_related_queries


class FindRelatedQueriesTestCase(SimpleTestCase):
    def test_ruttoh_synonyms(self):
        blobs = {1: ["быстро", "круто", "скоро"]}
        self.assertEqual(
            ["круто", "скоро"],
            find_related_queries({1}, blobs, {"быстро"}),
        )

    def test_skips_phrase_translations(self):
        blobs = {1: ["быстро", "быстро пробежать", "круто"]}
        self.assertEqual(["круто"], find_related_queries({1}, blobs, {"быстро"}))

    def test_dedupes_across_ilike_articles(self):
        blobs = {1: ["быстро", "круто"], 2: ["быстро", "круто", "скоро"]}
        self.assertEqual(
            ["круто", "скоро"],
            find_related_queries({1, 2}, blobs, {"быстро"}),
        )

    def test_no_ilike_hits_empty(self):
        self.assertEqual([], find_related_queries(set(), {1: ["круто"]}, {"быстро"}))

    def test_phrase_only_ilike_no_related(self):
        blobs = {2: ["быстро ехать"]}
        self.assertEqual([], find_related_queries({2}, blobs, {"быстро"}))

    def test_multiword_query_words_subtracted(self):
        blobs = {1: ["вон там", "вон", "там"]}
        self.assertEqual([], find_related_queries({1}, blobs, {"вон", "там"}))
