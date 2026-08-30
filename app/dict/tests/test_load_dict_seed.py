import json
import os
import tempfile
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TransactionTestCase, override_settings

from dict.models import (
    Article,
    ArticleIndexTranslate,
    ArticleIndexWord,
    ArticleIndexWordNormalization,
    Tag,
)


MINIMAL_FIXTURE = [
    {
        "model": "dict.tag",
        "pk": 1,
        "fields": {
            "tag": "test",
            "name": "test tag",
            "type": 2,
            "sorting": 1,
            "level": 0,
        },
    },
    {
        "model": "dict.article",
        "pk": 1,
        "fields": {
            "word": "aiga",
            "word_normalized": None,
            "first_letter": "A",
            "linked_article": None,
            "article_html": "<b>aiga</b>",
            "source": None,
            "source_detalization": None,
        },
    },
    {
        "model": "dict.articleindextranslate",
        "pk": 1,
        "fields": {
            "rus_word": "вода",
            "article": 1,
            "search_vector": None,
        },
    },
]


class LoadDictSeedTestCase(TransactionTestCase):
    def setUp(self):
        self.tag = Tag.objects.create(
            tag="old", name="old tag", type=2, sorting=1, level=0
        )
        self.article = Article.objects.create(word="oldword", article_html="<b>old</b>")
        ArticleIndexTranslate.objects.create(
            article=self.article, rus_word="старый"
        )

    def _write_fixture(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(MINIMAL_FIXTURE, f)
        return path

    @override_settings(DEBUG=True)
    def test_cancelled_without_yes_on_dev(self):
        path = self._write_fixture()
        try:
            with patch("builtins.input", return_value="n"):
                call_command("load_dict_seed", "--file", path, stdout=StringIO())
            self.assertTrue(Tag.objects.filter(pk=self.tag.pk).exists())
            self.assertTrue(Article.objects.filter(word="oldword").exists())
        finally:
            os.remove(path)

    @override_settings(DEBUG=True)
    def test_loads_fixture_and_reindexes(self):
        path = self._write_fixture()
        try:
            call_command(
                "load_dict_seed",
                "--file",
                path,
                "--yes",
                stdout=StringIO(),
            )
            self.assertFalse(Tag.objects.filter(tag="old").exists())
            self.assertTrue(Tag.objects.filter(tag="test").exists())
            art = Article.objects.get(word="aiga")
            self.assertTrue(
                ArticleIndexWord.objects.filter(article=art).exists()
            )
            self.assertTrue(
                ArticleIndexWordNormalization.objects.filter(article=art).exists()
            )
            tr = ArticleIndexTranslate.objects.get(article=art, rus_word="вода")
            self.assertIsNotNone(tr.search_vector)
        finally:
            os.remove(path)

    @override_settings(DEBUG=False)
    def test_production_requires_typed_yes(self):
        path = self._write_fixture()
        try:
            with patch("builtins.input", return_value="n"):
                call_command("load_dict_seed", "--file", path, stdout=StringIO())
            self.assertTrue(Article.objects.filter(word="oldword").exists())
        finally:
            os.remove(path)

    @override_settings(DEBUG=False)
    def test_production_allow_with_flags(self):
        path = self._write_fixture()
        try:
            call_command(
                "load_dict_seed",
                "--file",
                path,
                "--yes",
                "--allow-production",
                stdout=StringIO(),
            )
            self.assertTrue(Article.objects.filter(word="aiga").exists())
        finally:
            os.remove(path)
