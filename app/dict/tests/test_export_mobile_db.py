"""Tests for offline mobile SQLite export (schema_version = 2)."""

import json
import sqlite3
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from dict.mobile import SCHEMA_VERSION, export_mobile_package
from dict.mobile.schema import FORBIDDEN_TABLE_SUBSTRINGS
from dict.models import (
    Article,
    ArticleAddition,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleIndexWord,
    ArticleLink,
    Source,
    Tag,
)


class ExportMobileDbTestCase(TestCase):
    def setUp(self):
        self.source = Source.objects.create(title="Punzhina test")
        self.tag_pos = Tag.objects.create(
            tag="n.", name="substantivum", type=2, sorting=1, level=0
        )
        self.a = Article.objects.create(
            word="aiga",
            first_letter="A",
            article_html="<b>aiga</b> время",
            source=self.source,
        )
        self.b = Article.objects.create(
            word="boila",
            first_letter="B",
            article_html="<b>boila</b> см. aiga",
            source=self.source,
            linked_article=self.a,
        )
        # Article.save() already rebuilds ArticleIndexWord from word_index().
        if not ArticleIndexWord.objects.filter(article=self.a, word="aiga").exists():
            ArticleIndexWord.objects.create(article=self.a, word="aiga")
        ArticleIndexTranslate.objects.create(article=self.a, rus_word="время")
        ArticleIndexTag.objects.create(article=self.a, tag=self.tag_pos)
        ArticleAddition.objects.create(
            article=self.a, article_html="<i>add</i>", source=self.source
        )
        ArticleLink.objects.create(
            from_article=self.b,
            to_article=self.a,
            kind=ArticleLink.KIND_SEE,
        )

    def test_export_package_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = export_mobile_package(tmp)
            self.assertTrue(package.db_path.is_file())
            self.assertTrue(package.manifest_path.is_file())

            manifest = json.loads(package.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], SCHEMA_VERSION)
            self.assertEqual(manifest["file"], "dict.sqlite")
            self.assertEqual(manifest["url"], "dict.sqlite")
            self.assertEqual(manifest["sha256"], package.manifest["sha256"])
            self.assertEqual(manifest["size"], package.db_path.stat().st_size)
            self.assertTrue(manifest["data_version"])
            self.assertTrue(manifest["built_at"])
            self.assertEqual(len(manifest["sha256"]), 64)

            conn = sqlite3.connect(str(package.db_path))
            try:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                for needle in FORBIDDEN_TABLE_SUBSTRINGS:
                    self.assertFalse(
                        any(needle in t for t in tables),
                        f"forbidden table substring {needle!r} in {tables}",
                    )

                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0], 2
                )
                # Both articles get ArticleIndexWord rows from Article.save().
                self.assertGreaterEqual(
                    conn.execute("SELECT COUNT(*) FROM words").fetchone()[0], 2
                )
                self.assertTrue(
                    conn.execute(
                        "SELECT 1 FROM words WHERE word=? AND article_id=?",
                        ("aiga", self.a.id),
                    ).fetchone()
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0], 1
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM article_tags").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM additions").fetchone()[0], 1
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM links").fetchone()[0], 1
                )

                row = conn.execute(
                    "SELECT word, first_letter, sort_key, source_title, "
                    "linked_article_id FROM articles WHERE id=?",
                    (self.b.id,),
                ).fetchone()
                self.assertEqual(row[0], "boila")
                self.assertEqual(row[1], "B")
                self.assertTrue(row[2])  # opaque KRL sort key
                self.assertEqual(row[3], "Punzhina test")
                self.assertEqual(row[4], self.a.id)

                ordered = [
                    r[0]
                    for r in conn.execute(
                        "SELECT word FROM articles ORDER BY sort_key, id"
                    )
                ]
                self.assertEqual(ordered, ["aiga", "boila"])

                rus = conn.execute(
                    "SELECT article_id FROM translations WHERE rus_word LIKE ?",
                    ("%время%",),
                ).fetchone()
                self.assertEqual(rus[0], self.a.id)

                meta = dict(conn.execute("SELECT key, value FROM meta"))
                self.assertEqual(meta["schema_version"], str(SCHEMA_VERSION))
                self.assertIn("built_at", meta)
                self.assertEqual(meta["data_version"], manifest["data_version"])
                # data_version is a short content id; sha256 is of the final file.
                self.assertNotEqual(meta["data_version"], manifest["sha256"][:12])

                cols = {
                    row[1] for row in conn.execute("PRAGMA table_info(translations)")
                }
                self.assertIn("rus_word", cols)
                self.assertNotIn("rus_lemmas", cols)
                self.assertNotIn("search_vector", cols)
            finally:
                conn.close()

    def test_management_command_writes_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pack"
            call_command("export_mobile_db", out=str(out))
            self.assertTrue((out / "dict.sqlite").is_file())
            self.assertTrue((out / "manifest.json").is_file())
