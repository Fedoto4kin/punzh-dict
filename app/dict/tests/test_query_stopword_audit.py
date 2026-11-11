from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from dict.models import Article, ArticleIndexTranslate
from dict.query_stopword_audit import (
    format_python_set,
    scan_query_stopword_candidates,
)
from dict.search import STOPWORDS


class FormatPythonSetTestCase(SimpleTestCase):
    def test_empty(self):
        self.assertEqual(format_python_set("_STOP_1C", []), "_STOP_1C = set()\n")

    def test_sorted_quoted(self):
        text = format_python_set("_STOP_1C", ["при", "для"])
        self.assertIn('"для",', text)
        self.assertIn('"при",', text)
        self.assertTrue(text.startswith("_STOP_1C = {"))


class QueryStopwordAuditTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # High DF for «о» (already stop_1a) and «при» (candidate_1c).
        for i in range(5):
            art = Article.objects.create(word=f"w_o_{i}")
            ArticleIndexTranslate.objects.create(
                article=art, rus_word=f"первотельная (о корове {i})"
            )
        for i in range(5):
            art = Article.objects.create(word=f"w_pri_{i}")
            ArticleIndexTranslate.objects.create(
                article=art, rus_word=f"быть в охоте (при ком-л. {i})"
            )
        # Content word with low DF — not a candidate.
        art = Article.objects.create(word="w_korova")
        ArticleIndexTranslate.objects.create(article=art, rus_word="корова")
        # Short token not in STOPWORDS (synthetic gap).
        art = Article.objects.create(word="w_xx")
        ArticleIndexTranslate.objects.create(article=art, rus_word="хх слово")

    def test_buckets_and_paren_lead(self):
        audit = scan_query_stopword_candidates(min_df=3, max_len_1c=5, top=None)
        by_tok = {s.token: s for s in audit.stats}

        self.assertEqual(by_tok["о"].bucket, "stop_1a")
        self.assertGreaterEqual(by_tok["о"].paren_lead_df, 5)
        self.assertEqual(by_tok["при"].bucket, "candidate_1c")
        self.assertIn("при", audit.suggested_1c)
        self.assertEqual(by_tok["корова"].bucket, "content")
        self.assertNotIn("корова", STOPWORDS)

    def test_missing_1a_short_high_df(self):
        # «хх» appears once — below min_df=3 → content; raise with min_df=1.
        audit = scan_query_stopword_candidates(min_df=1, max_len_1c=5, top=None)
        by_tok = {s.token: s for s in audit.stats}
        self.assertEqual(by_tok["хх"].bucket, "missing_1a")
        self.assertIn("хх", audit.missing_1a)

    def test_command_stdout(self):
        out = StringIO()
        call_command(
            "audit_query_stopwords",
            "--min-df",
            "3",
            "--top",
            "20",
            "--suggest",
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("suggested_1c", text)
        self.assertIn("при", text)
        self.assertIn("_STOP_1C", text)

    def test_command_csv(self):
        out = StringIO()
        call_command(
            "audit_query_stopwords",
            "--min-df",
            "3",
            "--csv",
            "--bucket",
            "candidate_1c",
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("token,len,df,rows,paren_lead_df,bucket", text)
        self.assertIn("при,", text)
