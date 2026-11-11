"""Unit tests for Russian lemmatization (no DB)."""

from django.test import SimpleTestCase

from dict.helpers.rus_morph import lemma_token, lemmas_of_phrase, query_lemmas


class RusMorphLemmaTestCase(SimpleTestCase):
    def test_case_and_number(self):
        self.assertEqual(lemma_token("корове"), "корова")
        self.assertEqual(lemma_token("коров"), "корова")
        self.assertEqual(lemma_token("коровами"), "корова")
        self.assertEqual(lemma_token("человека"), "человек")
        self.assertEqual(lemma_token("людям"), "человек")
        self.assertEqual(lemma_token("воде"), "вода")

    def test_conjugation(self):
        self.assertEqual(lemma_token("едет"), "ехать")
        self.assertEqual(lemma_token("ехал"), "ехать")
        self.assertEqual(lemma_token("идем"), "идти")
        self.assertEqual(lemma_token("идёт"), "идти")
        self.assertEqual(lemma_token("идет"), "идти")
        self.assertEqual(lemma_token("говорит"), "говорить")

    def test_yo_canonical(self):
        # pymorphy often returns ё in normal_form; we store е.
        self.assertEqual(lemma_token("ребенка"), "ребенок")
        self.assertNotIn("ё", lemma_token("ребенка"))

    def test_adv_adj_not_merged(self):
        # Intentional: adverb vs adjective stay distinct (no stem bridge).
        self.assertEqual(lemma_token("быстро"), "быстро")
        self.assertEqual(lemma_token("быстрый"), "быстрый")
        self.assertEqual(lemma_token("быстрее"), "быстрый")
        self.assertNotEqual(lemma_token("быстро"), lemma_token("быстрый"))

    def test_ponizu_not_ponizit(self):
        self.assertNotEqual(lemma_token("понизу"), lemma_token("понизить"))

    def test_lemmas_of_phrase_unique(self):
        self.assertEqual(
            lemmas_of_phrase("первотельная (о корове)"),
            ["первотельный", "о", "корова"],
        )

    def test_query_lemmas(self):
        self.assertEqual(query_lemmas("корова"), ["корова"])
        self.assertEqual(query_lemmas("о корове"), ["о", "корова"])
