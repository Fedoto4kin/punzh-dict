from django.test import TestCase

from ..models import Article, ArticleIndexTranslate, ArticleLink
from ..search import search_by_translate_linked


# DB-backed (Postgres): exercises the full ?f= filter path in
# search_by_translate_linked (fulltext + ilike + expand + split + filter).
# Unlike the pure-function tests, these depend on the Postgres russian text
# search config and the custom __ilike lookup.


class SearchFilterTestCase(TestCase):
    def setUp(self):
        # ruttoh: only single-word synonyms -> base direct hit
        self.ruttoh = Article.objects.create(word="ruttoh")
        for rw in ["быстро", "круто", "скоро"]:
            ArticleIndexTranslate.objects.create(article=self.ruttoh, rus_word=rw)

        # maihahtua: has a phrase translation -> in выдача, NOT direct
        self.maihahtua = Article.objects.create(word="maihahtua")
        for rw in ["быстро", "быстро пробежать"]:
            ArticleIndexTranslate.objects.create(article=self.maihahtua, rus_word=rw)

        # ehatta: phrase "быстро ехать" -> narrowing tag "ехать"
        self.ehatta = Article.objects.create(word="ehatta")
        ArticleIndexTranslate.objects.create(
            article=self.ehatta, rus_word="быстро ехать"
        )

        # rutoldi: NO translations, linked to ruttoh -> inherited direct hit
        self.rutoldi = Article.objects.create(word="rutoldi")
        ArticleLink.objects.create(from_article=self.rutoldi, to_article=self.ruttoh)

    def test_no_filter_tags_and_direct_from_full_anchor(self):
        page_obj, found_count, narrowing, direct_ids = search_by_translate_linked(
            "быстро", 1, None
        )
        # весь кластер в выдаче: 4 статьи
        self.assertEqual(4, found_count)
        # теги от полного якоря: ключи "пробежать" и "ехать" (порядок не важен)
        self.assertEqual({"пробежать", "ехать"}, {t["key"] for t in narrowing})
        # прямые: ruttoh (базовое) + rutoldi (наследованное по связи)
        self.assertEqual({self.ruttoh.id, self.rutoldi.id}, set(direct_ids))

    def test_exact_filter_keeps_only_direct_hits(self):
        page_obj, found_count, narrowing, direct_ids = search_by_translate_linked(
            "быстро", 1, "exact"
        )
        self.assertEqual(2, found_count)
        self.assertEqual({"ruttoh", "rutoldi"}, {a.word for a in page_obj.object_list})
        # теги остаются полными (фильтр не пересчитывает якорь)
        self.assertEqual({"пробежать", "ехать"}, {t["key"] for t in narrowing})

    def test_key_filter_narrows_to_matching_cards(self):
        page_obj, found_count, narrowing, direct_ids = search_by_translate_linked(
            "быстро", 1, "ехать"
        )
        self.assertEqual(1, found_count)
        self.assertEqual({"ehatta"}, {a.word for a in page_obj.object_list})

    def test_inherited_direct_hit_present_in_exact(self):
        # rutoldi has no translations, only "см. ruttoh" -> must appear in exact
        page_obj, found_count, narrowing, direct_ids = search_by_translate_linked(
            "быстро", 1, "exact"
        )
        self.assertIn(self.rutoldi.id, set(direct_ids))
        self.assertIn("rutoldi", {a.word for a in page_obj.object_list})
