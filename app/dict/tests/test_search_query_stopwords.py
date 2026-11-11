"""P1: stop tokens dropped from multi-word Russian token-OR."""

from django.test import SimpleTestCase, TestCase

from dict.helpers import STOP_1C, STOPWORDS, tokens_for_token_or
from dict.models import Article, ArticleIndexTranslate
from dict.search import rus_search_core, search_by_translate_linked


class TokensForTokenOrTestCase(SimpleTestCase):
    def test_single_stop_kept(self):
        self.assertEqual(["о"], tokens_for_token_or(["о"]))
        self.assertEqual(["под"], tokens_for_token_or(["под"]))

    def test_multiword_drops_stops(self):
        self.assertEqual(["корове"], tokens_for_token_or(["о", "корове"]))
        self.assertEqual(["стола"], tokens_for_token_or(["под", "стола"]))

    def test_von_tam_kept(self):
        self.assertEqual(["вон", "там"], tokens_for_token_or(["вон", "там"]))

    def test_all_stops_kept(self):
        self.assertEqual(["для", "при"], tokens_for_token_or(["для", "при"]))

    def test_stop_1c_in_stopwords(self):
        for tok in STOP_1C:
            self.assertIn(tok, STOPWORDS)


class QueryStopwordOrSearchTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.enzi = Article.objects.create(word="enzi_stop")
        ArticleIndexTranslate.objects.create(
            article=cls.enzi, rus_word="первотельная (о корове)"
        )
        cls.bare_o = Article.objects.create(word="bare_o")
        ArticleIndexTranslate.objects.create(article=cls.bare_o, rus_word="о")
        cls.noise_o = Article.objects.create(word="noise_o_only")
        ArticleIndexTranslate.objects.create(article=cls.noise_o, rus_word="о погоде")
        cls.pod = Article.objects.create(word="pod_lemma")
        ArticleIndexTranslate.objects.create(article=cls.pod, rus_word="под")
        cls.pod_stol = Article.objects.create(word="pod_stol")
        ArticleIndexTranslate.objects.create(
            article=cls.pod_stol, rus_word="под столом"
        )
        cls.stol = Article.objects.create(word="stol_only")
        ArticleIndexTranslate.objects.create(article=cls.stol, rus_word="стол")

    def _ids(self, query, f=None):
        page, _, _, _, _, _ = search_by_translate_linked(query, 1, f)
        return {a.id for a in page.object_list}

    def test_o_korove_like_korove_without_bare_o_noise(self):
        # «о» is stop_1a: multi-word OR uses only «корова» lemma.
        found = self._ids("о корове")
        self.assertIn(self.enzi.id, found)
        self.assertNotIn(self.bare_o.id, found)
        self.assertNotIn(self.noise_o.id, found)
        core = rus_search_core("о корове")
        self.assertEqual(core.query_lemmas, ["корова"])

    def test_single_o_still_searches(self):
        found = self._ids("о")
        self.assertIn(self.bare_o.id, found)
        self.assertIn(self.noise_o.id, found)
        self.assertIn(self.enzi.id, found)

    def test_single_pod_still_searches(self):
        found = self._ids("под")
        self.assertIn(self.pod.id, found)
        self.assertIn(self.pod_stol.id, found)

    def test_pod_stol_drops_pod_from_or(self):
        found = self._ids("под стол")
        self.assertIn(self.stol.id, found)
        self.assertIn(self.pod_stol.id, found)
        # Bare «под» alone should not enter via stop OR.
        self.assertNotIn(self.pod.id, found)
        core = rus_search_core("под стол")
        self.assertEqual(core.query_lemmas, ["стол"])
