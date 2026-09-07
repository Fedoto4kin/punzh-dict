from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from dict.cyrillic_audit import (
    cyrillic_chars,
    find_html_cyrillic_leaks,
    suggest_latin,
)
from dict.models import Article

# Cyrillic а / р in otherwise Latin words.
CYR_A = "\u0430"
CYR_ER = "\u0440"
MIXED_TILDE = f"~{CYR_A}lla"
MIXED_MID = f"le{CYR_ER}pä"
LATIN = "leppä"


class CyrillicDetectorTestCase(SimpleTestCase):
    def test_latin_headword_is_clean(self):
        self.assertEqual(cyrillic_chars(LATIN), [])
        self.assertEqual(cyrillic_chars("müöd’ä"), [])
        self.assertEqual(cyrillic_chars("šoba"), [])

    def test_cyrillic_er_is_found(self):
        self.assertEqual(cyrillic_chars(MIXED_MID), [CYR_ER])

    def test_diaeresis_a_outside_ya_range(self):
        self.assertEqual(cyrillic_chars("lepp\u04d3"), ["\u04d3"])

    def test_suggest_maps_er_to_latin_p(self):
        self.assertEqual(suggest_latin(MIXED_MID), LATIN)


class HtmlLeakDetectorTestCase(SimpleTestCase):
    def test_tilde_cyrillic_flagged_even_if_all_cyrillic_homoglyphs(self):
        # ~ао — только кириллические омоглифы, без латиницы в токене.
        html = f"<b>x</b>; monella ~{CYR_A}\u043e voijiin"
        hits = find_html_cyrillic_leaks(html)
        kinds = {h["kind"] for h in hits}
        self.assertIn("after_tilde", kinds)
        self.assertTrue(any(h["value"] == f"~{CYR_A}\u043e" for h in hits))

    def test_tilde_mixed_reported_once_as_after_tilde(self):
        html = f"monella {MIXED_TILDE} voijiin"
        hits = find_html_cyrillic_leaks(html)
        self.assertEqual([h["kind"] for h in hits], ["after_tilde"])
        self.assertEqual(hits[0]["value"], MIXED_TILDE)
        self.assertEqual(hits[0]["suggested"], "~alla")

    def test_tilde_space_then_russian_gloss_ok(self):
        html = "ez’i on kaikkie paraš ~ мёд — самое лучшее лекарство;"
        self.assertEqual(find_html_cyrillic_leaks(html), [])

    def test_tilde_latin_continuation_ok(self):
        html = "monella ~alla voijiin, ~ мёд"
        self.assertEqual(find_html_cyrillic_leaks(html), [])

    def test_cyrillic_in_middle_of_latin_word(self):
        html = f"<b>{MIXED_MID}</b> <i>s</i> ольха"
        hits = find_html_cyrillic_leaks(html)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["kind"], "mixed")
        self.assertEqual(hits[0]["value"], MIXED_MID)
        self.assertEqual(hits[0]["suggested"], LATIN)

    def test_pure_russian_and_pure_karelian_ok(self):
        html = "<b>alla</b> мёд; harmuat ~ät серые глаза"
        self.assertEqual(find_html_cyrillic_leaks(html), [])

    def test_apostrophe_then_cyrillic_in_token(self):
        html = f"ez’{CYR_A} on kaikkie"
        hits = find_html_cyrillic_leaks(html)
        self.assertEqual([h["kind"] for h in hits], ["mixed"])
        self.assertEqual(hits[0]["value"], f"ez’{CYR_A}")


class AuditCyrillicLemmasCommandTestCase(TestCase):
    def test_reports_mixed_headword_not_translation(self):
        from dict.models import ArticleIndexTranslate

        dirty = Article.objects.create(word=MIXED_MID, article_html="<b>leppä</b>")
        clean = Article.objects.create(word=LATIN, article_html="<b>leppä</b>")
        ArticleIndexTranslate.objects.create(article=clean, rus_word="ольха")

        out = StringIO()
        call_command("audit_cyrillic_lemmas", stdout=out)
        text = out.getvalue()
        self.assertIn(f"#{dirty.id}", text)
        self.assertIn("Article.word", text)
        self.assertIn("CYRILLIC SMALL LETTER ER", text)
        self.assertIn(f"совпадёт со статьёй {clean.id}", text)
        self.assertNotIn("ольха", text)
        self.assertIn("1 статей", text)

    def test_csv_and_index_only(self):
        from dict.models import ArticleIndexWord

        art = Article.objects.create(word=LATIN, article_html="<b>leppä</b>")
        ArticleIndexWord.objects.filter(article=art).delete()
        idx = ArticleIndexWord.objects.create(article=art, word=MIXED_MID)

        out = StringIO()
        call_command("audit_cyrillic_lemmas", "--csv", stdout=out)
        text = out.getvalue()
        self.assertIn("article_id,field,value,chars,suggested,collision_id", text)
        self.assertIn(f"ArticleIndexWord.word#{idx.id}", text)
        self.assertIn(str(art.id), text)
        self.assertNotIn("Article.word", text)

    def test_clean_dictionary_prints_ok(self):
        Article.objects.create(word=LATIN, article_html="<b>leppä</b>")
        out = StringIO()
        call_command("audit_cyrillic_lemmas", stdout=out)
        self.assertIn("Кириллицы в заголовках и индексе нет", out.getvalue())


class AuditCyrillicHtmlCommandTestCase(TestCase):
    def test_reports_tilde_leak_in_html(self):
        art = Article.objects.create(
            word="alla",
            article_html=f"<b>alla</b>; monella {MIXED_TILDE} voijiin",
        )
        clean = Article.objects.create(
            word="mesi",
            article_html="<b>mesi</b>; ~ мёд — лекарство",
        )

        out = StringIO()
        call_command("audit_cyrillic_html", stdout=out)
        text = out.getvalue()
        self.assertIn(f"#{art.id}", text)
        self.assertIn("alla", text)
        self.assertIn("<b>alla</b>", text)
        self.assertIn("after_tilde", text)
        self.assertIn(MIXED_TILDE, text)
        self.assertNotIn(f"#{clean.id}", text)

    def test_csv_and_kind_filter(self):
        Article.objects.create(
            word="alla",
            article_html=f"<b>alla</b>; {MIXED_TILDE}; {MIXED_MID}",
        )
        out = StringIO()
        call_command(
            "audit_cyrillic_html", "--csv", "--kind", "after_tilde", stdout=out
        )
        text = out.getvalue()
        self.assertIn(
            "article_id,word,kind,homoglyph_only,value,offset,chars,suggested",
            text,
        )
        self.assertIn("after_tilde", text)
        self.assertIn(MIXED_TILDE, text)
        self.assertIn("alla", text)
        body = "\n".join(text.splitlines()[1:])
        self.assertNotIn(",mixed,", f",{body},")
        self.assertNotIn(MIXED_MID, body)

    def test_clean_html_prints_ok(self):
        Article.objects.create(word=LATIN, article_html=f"<b>{LATIN}</b> ольха; ~alla")
        out = StringIO()
        call_command("audit_cyrillic_html", stdout=out)
        self.assertIn("Кириллицы в карельских фрагментах HTML нет", out.getvalue())


class FixCyrillicHtmlCommandTestCase(TestCase):
    def test_dry_run_shows_word_and_article(self):
        art = Article.objects.create(
            word="alla",
            article_html=f"<b>alla</b>; monella {MIXED_TILDE} voijiin",
        )
        out = StringIO()
        call_command(
            "fix_cyrillic_html",
            "--dry-run",
            "--queue",
            "homoglyph",
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn(f"id={art.id}", text)
        self.assertIn("alla", text)
        self.assertIn(art.article_html, text)
        self.assertIn("~alla", text)  # suggested in proposal section

    def test_apply_y_rewrites_html(self):
        from unittest.mock import patch

        from dict.management.commands.fix_cyrillic_html import Command

        art = Article.objects.create(
            word="alla",
            article_html=f"<b>alla</b>; monella {MIXED_TILDE} voijiin",
        )
        answers = iter(["y"])
        out = StringIO()
        with patch.object(
            Command, "_ask", side_effect=lambda prompt: next(answers)
        ), patch(
            "dict.management.commands.fix_cyrillic_html.sys.stdin.isatty",
            return_value=True,
        ):
            call_command(
                "fix_cyrillic_html",
                "--queue",
                "homoglyph",
                "--id",
                str(art.id),
                stdout=out,
            )
        art.refresh_from_db()
        self.assertIn("~alla", art.article_html)
        self.assertNotIn(MIXED_TILDE, art.article_html)
        self.assertIn("HTML обновлён — 1", out.getvalue())

    def test_apply_token_fix_helper(self):
        from dict.cyrillic_audit import apply_token_fix, is_homoglyph_only

        html = f"monella {MIXED_TILDE} x"
        self.assertEqual(
            apply_token_fix(html, MIXED_TILDE, "~alla"),
            "monella ~alla x",
        )
        self.assertTrue(is_homoglyph_only([CYR_A]))
        self.assertFalse(is_homoglyph_only([CYR_A, "\u043d"]))  # н
