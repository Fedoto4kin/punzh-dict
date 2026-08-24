import json
import os
import tempfile

from django.core.management import call_command
from django.test import TestCase

from ..models import Article, ArticleSemanticField, SemanticField


class ArticleSemanticFieldFromTranslationTestCase(TestCase):
    def setUp(self):
        self.animals = SemanticField.objects.create(
            name="Животные",
            definition="Животный мир",
            sorting=1,
        )
        self.flax = SemanticField.objects.create(
            name="Лён",
            definition="Растение",
            sorting=2,
        )
        self.art = Article.objects.create(word="aiga")
        self.other = Article.objects.create(word="muu")

    def test_two_from_translation_on_same_article_ok(self):
        ArticleSemanticField.objects.create(
            article=self.art, field=self.animals, from_translation=True
        )
        ArticleSemanticField.objects.create(
            article=self.art, field=self.flax, from_translation=True
        )
        self.assertEqual(
            2, self.art.semantic_assignments.filter(from_translation=True).count()
        )

    def test_all_false_ok(self):
        ArticleSemanticField.objects.create(article=self.art, field=self.animals)
        ArticleSemanticField.objects.create(article=self.art, field=self.flax)
        self.assertFalse(
            self.art.semantic_assignments.filter(from_translation=True).exists()
        )


class LoadTranslationFieldsTestCase(TestCase):
    def setUp(self):
        self.animals = SemanticField.objects.create(name="Животные", sorting=1)
        self.flax = SemanticField.objects.create(name="Лён", sorting=2)
        self.art = Article.objects.create(word="aiga")
        self.other = Article.objects.create(word="muu")
        ArticleSemanticField.objects.create(article=self.art, field=self.animals)
        ArticleSemanticField.objects.create(article=self.art, field=self.flax)
        ArticleSemanticField.objects.create(article=self.other, field=self.flax)

    def _load(self, mapping):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"from_translation": mapping}, f)
            call_command("load_translation_fields", "--file", path)
        finally:
            os.remove(path)

    def test_sets_two_fields_on_one_article(self):
        self._load({str(self.art.id): ["Животные", "Лён"]})
        self.assertTrue(
            self.art.semantic_assignments.get(field=self.animals).from_translation
        )
        self.assertTrue(
            self.art.semantic_assignments.get(field=self.flax).from_translation
        )
        self.assertFalse(
            self.other.semantic_assignments.get(field=self.flax).from_translation
        )

    def test_empty_list_clears_flags(self):
        ArticleSemanticField.objects.filter(article=self.art, field=self.animals).update(
            from_translation=True
        )
        self._load({str(self.art.id): []})
        self.assertFalse(
            self.art.semantic_assignments.filter(from_translation=True).exists()
        )

    def test_unknown_field_name_skips_that_name(self):
        ArticleSemanticField.objects.filter(article=self.art, field=self.animals).update(
            from_translation=True
        )
        self._load({str(self.art.id): ["Нет такого поля"]})
        self.assertFalse(
            self.art.semantic_assignments.filter(from_translation=True).exists()
        )

    def test_missing_link_does_not_create_assignment(self):
        self._load({str(self.other.id): ["Животные"]})
        self.assertFalse(
            self.other.semantic_assignments.filter(field=self.animals).exists()
        )
        self.assertFalse(
            self.other.semantic_assignments.filter(from_translation=True).exists()
        )
