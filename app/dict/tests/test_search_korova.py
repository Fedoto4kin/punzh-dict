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

    def test_korova_finds_phrase_via_fuzzy_token(self):
        page_obj, found_count, narrowing, direct_ids, _ = search_by_translate_linked(
            "корова", 1, None
        )
        words = {a.word for a in page_obj.object_list}
        self.assertIn(self.enzi.word, words)
        self.assertIn(self.decoy.word, words)
        self.assertNotIn(self.enzi.id, direct_ids)

    def test_korova_narrowing_label_keeps_parens(self):
        _, _, narrowing, _, _ = search_by_translate_linked("корова", 1, None)
        enzi_tags = [t for t in narrowing if t["key"].startswith("первотельная")]
        self.assertTrue(enzi_tags)
        self.assertIn("(о корове)", enzi_tags[0]["label"])

    def test_korova_filter_by_pervotelnaia(self):
        page_obj, found_count, _, _, _ = search_by_translate_linked(
            "корова", 1, "первотельная"
        )
        self.assertEqual(1, found_count)
        self.assertEqual({self.enzi.word}, {a.word for a in page_obj.object_list})

    def test_pervotelnaia_korova_exact_ilike(self):
        ArticleIndexTranslate.objects.create(
            article=self.enzi,
            rus_word="первотельная корова",
        )
        _, _, _, direct_ids, _ = search_by_translate_linked(
            "первотельная корова", 1, None
        )
        self.assertIn(self.enzi.id, direct_ids)


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
        _, found_count, narrowing, direct_ids, _ = search_by_translate_linked(
            "быть", 1, None
        )
        self.assertGreater(found_count, 1)
        self.assertLessEqual(len(narrowing), 5)
        self.assertIn(self.olla.id, direct_ids)
        keys = {t["key"] for t in narrowing}
        self.assertIn("обиде", keys)
