from django.test import TestCase

from ..models import Article, ArticleIndexTranslate
from ..search import search_by_translate_linked


class KorovaNarrowingTestCase(TestCase):
    """Эталон enži|kandon'e / «корова» (searching_upgrade §0.1, backlog §2)."""

    @classmethod
    def setUpTestData(cls):
        cls.enzi = Article.objects.create(word="enzi|kandon'e")
        ArticleIndexTranslate.objects.create(
            article=cls.enzi,
            rus_word="первотельная (о корове)",
        )
        cls.decoy = Article.objects.create(word="korova_decoy")
        ArticleIndexTranslate.objects.create(
            article=cls.decoy,
            rus_word="корова",
        )
        cls.other = Article.objects.create(word="other_cow")
        ArticleIndexTranslate.objects.create(
            article=cls.other,
            rus_word="дойная корова",
        )

    def test_korova_finds_phrase_via_lemma_token(self):
        page_obj, found_count, narrowing, direct_ids, _, _ = search_by_translate_linked(
            "корова", 1, None
        )
        words = {a.word for a in page_obj.object_list}
        self.assertIn(self.enzi.word, words)
        self.assertIn(self.decoy.word, words)
        self.assertNotIn(self.enzi.id, direct_ids)

    def test_korova_narrowing_label_keeps_parens(self):
        _, _, narrowing, _, _, _ = search_by_translate_linked("корова", 1, None)
        enzi_tags = [t for t in narrowing if t["key"].startswith("первотельная")]
        self.assertTrue(enzi_tags)
        self.assertIn("(о корове)", enzi_tags[0]["label"])

    def test_korova_filter_by_pervotelnaia(self):
        page_obj, found_count, _, _, _, _ = search_by_translate_linked(
            "корова", 1, "первотельная"
        )
        self.assertEqual(1, found_count)
        self.assertEqual({self.enzi.word}, {a.word for a in page_obj.object_list})

    def test_korova_filter_excludes_paren_only_cow_gloss(self):
        gloss_only = Article.objects.create(word="heat_cow")
        ArticleIndexTranslate.objects.create(
            article=gloss_only,
            rus_word="быть в охоте (о корове)",
        )
        page_obj, found_count, _, _, _, _ = search_by_translate_linked(
            "корова", 1, "первотельная"
        )
        self.assertEqual(1, found_count)
        self.assertEqual({self.enzi.word}, {a.word for a in page_obj.object_list})

    def test_korova_legacy_f_with_korove_requires_both_tokens(self):
        gloss_only = Article.objects.create(word="heat_cow2")
        ArticleIndexTranslate.objects.create(
            article=gloss_only,
            rus_word="быть в охоте (о корове)",
        )
        page_obj, found_count, _, _, _, _ = search_by_translate_linked(
            "корова", 1, "первотельная корове"
        )
        self.assertEqual(1, found_count)
        self.assertEqual({self.enzi.word}, {a.word for a in page_obj.object_list})

    def test_pervotelnaia_korova_exact_ilike(self):
        ArticleIndexTranslate.objects.create(
            article=self.enzi,
            rus_word="первотельная корова",
        )
        _, _, _, direct_ids, _, _ = search_by_translate_linked(
            "первотельная корова", 1, None
        )
        self.assertIn(self.enzi.id, direct_ids)


class LemmaMorphologySearchTestCase(TestCase):
    """P3: case/conjugation match via rus_lemmas, without one-letter fuzzy."""

    @classmethod
    def setUpTestData(cls):
        cls.chelovek = Article.objects.create(word="ihmine")
        ArticleIndexTranslate.objects.create(article=cls.chelovek, rus_word="человек")
        cls.cheloveka = Article.objects.create(word="ihmist")
        ArticleIndexTranslate.objects.create(
            article=cls.cheloveka, rus_word="для человека"
        )
        cls.ljudjam = Article.objects.create(word="rahvahile")
        ArticleIndexTranslate.objects.create(article=cls.ljudjam, rus_word="людям")
        cls.ehat = Article.objects.create(word="ajea")
        ArticleIndexTranslate.objects.create(article=cls.ehat, rus_word="едет быстро")
        cls.mena = Article.objects.create(word="menna")
        ArticleIndexTranslate.objects.create(article=cls.mena, rus_word="идёт домой")
        cls.von = Article.objects.create(word="von_stench")
        ArticleIndexTranslate.objects.create(article=cls.von, rus_word="вонь")

    def _ids(self, query, f=None):
        page, _, _, _, _, _ = search_by_translate_linked(query, 1, f)
        return {a.id for a in page.object_list}

    def test_chelovek_finds_genitive_and_suppletive(self):
        found = self._ids("человек")
        self.assertIn(self.chelovek.id, found)
        self.assertIn(self.cheloveka.id, found)
        self.assertIn(self.ljudjam.id, found)

    def test_ehat_conjugation(self):
        self.assertIn(self.ehat.id, self._ids("ехать"))

    def test_idti_conjugation(self):
        self.assertIn(self.mena.id, self._ids("идти"))
        self.assertIn(self.mena.id, self._ids("идет"))

    def test_von_not_von_stench(self):
        self.assertNotIn(self.von.id, self._ids("вон"))


class PonizuNarrowingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.exact = Article.objects.create(word="ponizu")
        ArticleIndexTranslate.objects.create(article=cls.exact, rus_word="понизу")
        cls.verb = Article.objects.create(word="ponizit")
        ArticleIndexTranslate.objects.create(article=cls.verb, rus_word="понизить цену")

    def test_ponizu_no_spurious_narrowing_tags(self):
        _, _, narrowing, direct_ids, _, _ = search_by_translate_linked(
            "понизу", 1, None
        )
        self.assertEqual([], narrowing)
        self.assertIn(self.exact.id, direct_ids)


class HighFreqAnchorTestCase(TestCase):
    def setUp(self):
        self.olla = Article.objects.create(word="olla")
        ArticleIndexTranslate.objects.create(article=self.olla, rus_word="быть")
        ArticleIndexTranslate.objects.create(article=self.olla, rus_word="быть в обиде")
        for i in range(8):
            art = Article.objects.create(word=f"noise{i}")
            ArticleIndexTranslate.objects.create(
                article=art, rus_word=f"быть в состоянии {i}"
            )

    def test_byt_prio_limits_narrowing_tags(self):
        _, found_count, narrowing, direct_ids, _, _ = search_by_translate_linked(
            "быть", 1, None
        )
        self.assertGreater(found_count, 1)
        self.assertLessEqual(len(narrowing), 5)
        self.assertIn(self.olla.id, direct_ids)
        keys = {t["key"] for t in narrowing}
        self.assertIn("обиде", keys)
