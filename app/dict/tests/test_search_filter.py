from django.test import TestCase

from ..models import Article, ArticleIndexTranslate, ArticleLink
from ..search import search_by_translate_linked


# DB-backed (Postgres): exercises the full ?f= filter path in
# search_by_translate_linked (ILIKE + token OR + expand + split + filter).


class SearchFilterTestCase(TestCase):
    def setUp(self):
        # ruttoh: ILIKE hit on «быстро»
        self.ruttoh = Article.objects.create(word="ruttoh")
        for rw in ["быстро", "круто", "скоро"]:
            ArticleIndexTranslate.objects.create(article=self.ruttoh, rus_word=rw)

        # maihahtua: ILIKE on «быстро» plus a phrase translation
        self.maihahtua = Article.objects.create(word="maihahtua")
        for rw in ["быстро", "быстро пробежать"]:
            ArticleIndexTranslate.objects.create(article=self.maihahtua, rus_word=rw)

        # ehatta: phrase only — in выдача via FTS, not exact
        self.ehatta = Article.objects.create(word="ehatta")
        ArticleIndexTranslate.objects.create(
            article=self.ehatta, rus_word="быстро ехать"
        )

        # rutoldi: NO translations, linked to ruttoh -> inherited exact hit
        self.rutoldi = Article.objects.create(word="rutoldi")
        ArticleLink.objects.create(from_article=self.rutoldi, to_article=self.ruttoh)

        # linkedown: linked to ruttoh but own translations don't match query
        self.linkedown = Article.objects.create(word="linkedown")
        ArticleIndexTranslate.objects.create(
            article=self.linkedown, rus_word="медленно"
        )
        ArticleLink.objects.create(from_article=self.linkedown, to_article=self.ruttoh)

    def test_no_filter_tags_and_exact_from_full_anchor(self):
        page_obj, found_count, narrowing, direct_ids, related = (
            search_by_translate_linked("быстро", 1, None)
        )
        self.assertEqual(["круто", "скоро"], related)
        # весь кластер в выдаче: 5 статей
        self.assertEqual(5, found_count)
        self.assertEqual({"пробежать", "ехать"}, {t["key"] for t in narrowing})
        # точные: ILIKE + наследование, без linkedown и ehatta
        self.assertEqual(
            {self.ruttoh.id, self.rutoldi.id, self.maihahtua.id},
            set(direct_ids),
        )

    def test_exact_filter_keeps_ilike_and_inherited_only(self):
        page_obj, found_count, narrowing, direct_ids, _ = search_by_translate_linked(
            "быстро", 1, "exact"
        )
        self.assertEqual(3, found_count)
        self.assertEqual(
            {"ruttoh", "rutoldi", "maihahtua"},
            {a.word for a in page_obj.object_list},
        )
        self.assertEqual({"пробежать", "ехать"}, {t["key"] for t in narrowing})

    def test_key_filter_narrows_to_matching_cards(self):
        page_obj, found_count, narrowing, direct_ids, _ = search_by_translate_linked(
            "быстро", 1, "ехать"
        )
        self.assertEqual(1, found_count)
        self.assertEqual({"ehatta"}, {a.word for a in page_obj.object_list})

    def test_inherited_exact_hit_present(self):
        page_obj, found_count, narrowing, direct_ids, _ = search_by_translate_linked(
            "быстро", 1, "exact"
        )
        self.assertIn(self.rutoldi.id, set(direct_ids))
        self.assertIn("rutoldi", {a.word for a in page_obj.object_list})

    def test_linked_with_own_translations_excluded_from_exact(self):
        page_obj, found_count, narrowing, direct_ids, _ = search_by_translate_linked(
            "быстро", 1, "exact"
        )
        self.assertNotIn(self.linkedown.id, set(direct_ids))
        self.assertNotIn("linkedown", {a.word for a in page_obj.object_list})
