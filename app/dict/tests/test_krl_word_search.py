"""Public Karelian word search (exact ILIKE via ArticleIndexWord)."""

from django.test import Client, SimpleTestCase, TestCase

from ..models import Article, ArticleIndexWord, ArticleIndexWordNormalization
from ..search import krl_article_ids, prepare_krl_ilike_query, word_search
from ..see_audit import fold_lemma, html_see_lemmas, link_see_lemmas


class PrepareKrlIlikeQueryPublicTestCase(SimpleTestCase):
    def test_question_and_dot(self):
        self.assertEqual("ai%", prepare_krl_ilike_query("ai?"))
        self.assertEqual("ai_", prepare_krl_ilike_query("ai."))

    def test_folds_sibilants_apostrophes_and_interior_hyphen(self):
        self.assertEqual("soba", prepare_krl_ilike_query("šoba"))
        self.assertEqual("mullin", prepare_krl_ilike_query("mul’l’in"))
        self.assertEqual("mullin", prepare_krl_ilike_query("mul'l'in"))
        self.assertEqual("mullin", prepare_krl_ilike_query("mulʼlʼin"))
        self.assertEqual("mullin mallin", prepare_krl_ilike_query("mul’l’in-mal’l’in"))
        self.assertEqual(
            "mullin mallin", prepare_krl_ilike_query("mulʼlʼin-malʼlʼin")
        )
        self.assertEqual("siksi", prepare_krl_ilike_query("šiksi…"))
        self.assertEqual("siksi sto", prepare_krl_ilike_query("šiksi… što"))

    def test_folds_u_umlaut_to_y_like_sibilants(self):
        self.assertEqual("hyckähtiä", prepare_krl_ilike_query("hüčkähtiä"))
        self.assertEqual("hyckähtiä", prepare_krl_ilike_query("hyčkähtiä"))
        self.assertEqual("Hyckähtiä", prepare_krl_ilike_query("Hüčkähtiä"))
        self.assertEqual("hyckäht%", prepare_krl_ilike_query("hüčkäht?"))

    def test_leading_hyphen_kept(self):
        self.assertEqual("-raiska", prepare_krl_ilike_query("-raiska"))


class KrlArticleIdsTestCase(TestCase):
    def setUp(self):
        self.aiga = Article.objects.create(word="aiga")
        self.aika = Article.objects.create(word="aika")
        self.aia = Article.objects.create(word="aia")
        self.soba = Article.objects.create(word="šoba")
        self.phrase = Article.objects.create(word="mul’l’in mal’l’in")
        self.phrase_u = Article.objects.create(word="mül’l’in mäl’l’in")
        self.hyphen_hw = Article.objects.create(word="l’en’d’el’ijä-orava")
        self.old_u = Article.objects.create(word="hüčkäht’||iä")
        self.new_y = Article.objects.create(word="hyčkäht’iä")
        self.ellipsis = Article.objects.create(word="šiksi… što")

    def _ids(self, query):
        return set(krl_article_ids(query))

    def test_exact_headword(self):
        self.assertEqual(self._ids("aiga"), {self.aiga.id})

    def test_exact_is_not_prefix(self):
        self.assertEqual(self._ids("ai"), set())

    def test_question_matches_any_tail(self):
        self.assertEqual(self._ids("ai?"), {self.aiga.id, self.aika.id, self.aia.id})

    def test_dot_matches_one_character(self):
        self.assertEqual(self._ids("ai."), {self.aia.id})

    def test_query_sibilant_folds_to_indexed_form(self):
        self.assertEqual(self._ids("šoba"), {self.soba.id})
        self.assertEqual(self._ids("soba"), {self.soba.id})

    def test_index_keeps_phrase_tokens_and_hyphen(self):
        indexed = set(
            ArticleIndexWord.objects.filter(article=self.phrase).values_list(
                "word", flat=True
            )
        )
        self.assertEqual(
            indexed, {"mullin mallin", "mullin", "mallin", "mullin-mallin"}
        )

    def test_normalization_index_keeps_all_tokens(self):
        norms = set(
            ArticleIndexWordNormalization.objects.filter(
                article=self.phrase
            ).values_list("word", flat=True)
        )
        self.assertEqual(norms, {"mullin", "mallin"})

    def test_two_word_full_phrase_matches(self):
        self.assertEqual(self._ids("mullin mallin"), {self.phrase.id})
        self.assertEqual(self._ids("mul’l’in mal’l’in"), {self.phrase.id})
        self.assertEqual(self._ids("mulʼlʼin malʼlʼin"), {self.phrase.id})

    def test_hyphenated_see_form_finds_spaced_headword(self):
        self.assertEqual(self._ids("mullin-mallin"), {self.phrase.id})
        self.assertEqual(self._ids("mul’l’in-mal’l’in"), {self.phrase.id})
        self.assertEqual(self._ids("mulʼlʼin-malʼlʼin"), {self.phrase.id})

    def test_modifier_letter_apostrophe_single_token(self):
        self.assertEqual(self._ids("mulʼlʼin"), {self.phrase.id})

    def test_two_word_u_variants_full_phrase(self):
        self.assertEqual(self._ids("müllin mällin"), {self.phrase_u.id})
        self.assertEqual(self._ids("myllin mällin"), {self.phrase_u.id})

    def test_two_word_single_token_hits(self):
        self.assertEqual(self._ids("mullin"), {self.phrase.id})
        self.assertEqual(self._ids("mallin"), {self.phrase.id})
        self.assertEqual(self._ids("mällin"), {self.phrase_u.id})
        self.assertEqual(self._ids("müllin"), {self.phrase_u.id})
        self.assertEqual(self._ids("myllin"), {self.phrase_u.id})

    def test_hyphen_headword_searchable_both_ways(self):
        self.assertIn(self.hyphen_hw.id, self._ids("lendelijä-orava"))
        self.assertIn(self.hyphen_hw.id, self._ids("lendelijä orava"))
        self.assertIn(self.hyphen_hw.id, self._ids("orava"))

    def test_prefix_wildcard_reaches_into_phrase(self):
        self.assertEqual(self._ids("mullin?"), {self.phrase.id})

    def test_y_headword_index_keeps_normalized_form_only(self):
        indexed = set(
            ArticleIndexWord.objects.filter(article=self.new_y).values_list(
                "word", flat=True
            )
        )
        self.assertEqual(indexed, {"hyckähtiä"})

    def test_u_headword_index_keeps_both_orthographies(self):
        indexed = set(
            ArticleIndexWord.objects.filter(article=self.old_u).values_list(
                "word", flat=True
            )
        )
        self.assertEqual(indexed, {"hyckähtiä", "hückähtiä"})

    def test_u_query_finds_already_normalized_headword(self):
        self.assertIn(self.new_y.id, self._ids("hüčkähtiä"))

    def test_u_and_y_queries_find_both_orthographies(self):
        expected = {self.old_u.id, self.new_y.id}
        self.assertEqual(self._ids("hüčkähtiä"), expected)
        self.assertEqual(self._ids("hyčkähtiä"), expected)
        self.assertEqual(self._ids("hüčkäht?"), expected)

    def test_ellipsis_headword_index_splits_like_comma(self):
        indexed = set(
            ArticleIndexWord.objects.filter(article=self.ellipsis).values_list(
                "word", flat=True
            )
        )
        self.assertEqual(indexed, {"siksi", "sto"})
        norms = set(
            ArticleIndexWordNormalization.objects.filter(
                article=self.ellipsis
            ).values_list("word", flat=True)
        )
        self.assertEqual(norms, {"šiksi", "što"})

    def test_ellipsis_headword_searchable_by_each_part(self):
        self.assertEqual(self._ids("šiksi"), {self.ellipsis.id})
        self.assertEqual(self._ids("siksi"), {self.ellipsis.id})
        self.assertEqual(self._ids("što"), {self.ellipsis.id})


class SeeHyphenLinkTestCase(SimpleTestCase):
    def test_link_keeps_hyphenated_lemma(self):
        src = "<i>см.</i> mul’l’in-mal’l’in; ~ langein"
        self.assertEqual(html_see_lemmas(src), ["mul’l’in-mal’l’in"])
        html = link_see_lemmas(src)
        self.assertIn('<a href="/search/mul’l’in-mal’l’in">mul’l’in-mal’l’in</a>', html)
        self.assertNotIn('href="/search/mul’l’in"', html)

    def test_link_keeps_spaced_lemma(self):
        src = (
            "<b>kur’in murin</b> <i>adv</i> <i>см.</i> kur’iin mur’iin; "
            "mukelduači pordahilda ~"
        )
        self.assertEqual(html_see_lemmas(src), ["kur’iin mur’iin"])
        html = link_see_lemmas(src)
        self.assertIn('<a href="/search/kur’iin%20mur’iin">kur’iin mur’iin</a>', html)
        self.assertNotIn('href="/search/kur’iin"', html)
        self.assertNotIn("mukelduači</a>", html)

    def test_fold_lemma_equates_hyphen_and_space(self):
        self.assertEqual(
            fold_lemma("mul’l’in-mal’l’in"), fold_lemma("mul’l’in mal’l’in")
        )


class WordSearchHttpTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.aiga = Article.objects.create(word="aiga")
        self.phrase = Article.objects.create(word="mul’l’in mal’l’in")

    def test_search_path_returns_hit(self):
        response = self.client.get("/search/aiga")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "aiga")

    def test_search_proc_redirects_stripped_phrase(self):
        response = self.client.get(
            "/search/", {"query": "mul’l’in mal’l’in"}, follow=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/search/mullin%20mallin")

    def test_search_proc_keeps_modifier_letter_apostrophe(self):
        response = self.client.get(
            "/search/", {"query": "mulʼlʼin malʼlʼin"}, follow=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "/search/mul%CA%BCl%CA%BCin%20mal%CA%BCl%CA%BCin",
        )

    def test_search_modifier_letter_apostrophe_path_shows_article(self):
        response = self.client.get("/search/mul%CA%BCl%CA%BCin%20mal%CA%BCl%CA%BCin")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mullin mallin")

    def test_search_hyphen_form_shows_article(self):
        response = self.client.get(
            "/search/", {"query": "mul’l’in-mal’l’in"}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mullin mallin")

    def test_search_phrase_path_shows_article(self):
        response = self.client.get("/search/mullin%20mallin")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mullin mallin")

    def test_search_single_token_shows_article(self):
        response = self.client.get("/search/mallin")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mullin mallin")

    def test_word_search_paginator(self):
        page_obj, found_count = word_search("aiga", 1)
        self.assertEqual(found_count, 1)
        self.assertEqual([a.word for a in page_obj.object_list], ["aiga"])
