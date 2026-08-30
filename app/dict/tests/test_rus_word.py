from django.test import TestCase

from dict.helpers.rus_word import canonical_rus_word, dedupe_canonical_rus_words
from dict.models import Article, ArticleIndexTranslate
from dict.translation_index_write import apply_translations


class RusWordCanonicalTests(TestCase):
    def test_canonical_yo_to_e(self):
        self.assertEqual(canonical_rus_word("  мёд  "), "мед")
        self.assertEqual(canonical_rus_word("лёгкий"), "легкий")

    def test_dedupe_canonical_rus_words(self):
        self.assertEqual(
            dedupe_canonical_rus_words(["мед", "мёд", "МЁД", "  мёд  "]),
            ["мед"],
        )


class ArticleIndexTranslateSaveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.article = Article.objects.create(word="med_test")

    def test_save_normalizes_yo(self):
        row = ArticleIndexTranslate.objects.create(article=self.article, rus_word="мёд")
        row.refresh_from_db()
        self.assertEqual(row.rus_word, "мед")

    def test_save_skips_duplicate_after_canonicalization(self):
        ArticleIndexTranslate.objects.create(article=self.article, rus_word="мед")
        before = ArticleIndexTranslate.objects.filter(article=self.article).count()
        ArticleIndexTranslate.objects.create(article=self.article, rus_word="мёд")
        after = ArticleIndexTranslate.objects.filter(article=self.article).count()
        self.assertEqual(before, after)
        self.assertEqual(
            list(
                ArticleIndexTranslate.objects.filter(article=self.article).values_list(
                    "rus_word", flat=True
                )
            ),
            ["мед"],
        )

    def test_save_update_to_duplicate_removes_extra_row(self):
        first = ArticleIndexTranslate.objects.create(
            article=self.article, rus_word="мед"
        )
        second = ArticleIndexTranslate.objects.create(
            article=self.article, rus_word="сок"
        )
        second.rus_word = "мёд"
        second.save()
        self.assertFalse(ArticleIndexTranslate.objects.filter(pk=second.pk).exists())
        self.assertTrue(ArticleIndexTranslate.objects.filter(pk=first.pk).exists())


class ApplyTranslationsDedupeTests(TestCase):
    def test_apply_translations_dedupes_yo_variants(self):
        article = Article.objects.create(word="huni")
        apply_translations(article.id, ["мед", "мёд", "сок"])
        words = list(
            ArticleIndexTranslate.objects.filter(article=article)
            .order_by("rus_word")
            .values_list("rus_word", flat=True)
        )
        self.assertEqual(words, ["мед", "сок"])
