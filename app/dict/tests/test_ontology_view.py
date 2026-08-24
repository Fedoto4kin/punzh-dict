from django.test import Client, TestCase

from ..models import (
    Article,
    ArticleIndexTag,
    ArticleLink,
    ArticleSemanticField,
    SemanticField,
    Tag,
)
from ..search import num_by_page, search_by_semantic_field


class OntologyViewTestCase(TestCase):
    def setUp(self):
        self.c = Client()
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
        self.empty = SemanticField.objects.create(
            name="Пустое поле",
            definition="",
            sorting=3,
        )

        self.aiga = Article.objects.create(word="aiga")
        self.bua = Article.objects.create(word="bua")
        self.ciga = Article.objects.create(word="ciga")
        self.other = Article.objects.create(word="muu")

        ArticleSemanticField.objects.create(article=self.ciga, field=self.animals)
        ArticleSemanticField.objects.create(article=self.aiga, field=self.animals)
        ArticleSemanticField.objects.create(article=self.bua, field=self.animals)
        ArticleSemanticField.objects.create(article=self.other, field=self.flax)

        self.see_also = Article.objects.create(word="aah")
        ArticleLink.objects.create(from_article=self.see_also, to_article=self.aiga)

        tag = Tag.objects.create(tag="сущ.", name="существительное", type=2)
        ArticleIndexTag.objects.create(article=self.aiga, tag=tag)
        ArticleLink.objects.create(from_article=self.aiga, to_article=self.other)

    def test_index_is_not_letter_pointer(self):
        response = self.c.get("/ontology/")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Животные")
        self.assertContains(response, "Лён")

    def test_unknown_id_is_404(self):
        response = self.c.get("/ontology/99999/")
        self.assertEqual(404, response.status_code)

    def test_field_lists_only_its_articles_in_krl_order(self):
        response = self.c.get("/ontology/%s/" % self.animals.id)
        self.assertEqual(200, response.status_code)
        words = [a.word for a in response.context["page_obj"].object_list]
        self.assertEqual(["aah", "aiga", "bua", "ciga"], words)
        self.assertNotIn("muu", words)

    def test_search_helper_matches_view(self):
        content = search_by_semantic_field(self.animals.id, 1)
        words = [a.word for a in content.page_obj.object_list]
        self.assertEqual(["aah", "aiga", "bua", "ciga"], words)

    def test_article_keeps_tag_link_and_field(self):
        self.assertTrue(self.aiga.articleindextag_set.filter(tag__tag="сущ.").exists())
        self.assertTrue(self.aiga.links_from.filter(to_article=self.other).exists())
        self.assertTrue(
            self.aiga.semantic_assignments.filter(field=self.animals).exists()
        )
        response = self.c.get("/ontology/%s/" % self.animals.id)
        words = [a.word for a in response.context["page_obj"].object_list]
        self.assertIn("aiga", words)

    def test_empty_field_is_200_with_no_articles(self):
        response = self.c.get("/ontology/%s/" % self.empty.id)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], list(response.context["page_obj"].object_list))
        self.assertContains(response, "пока нет статей")

    def test_pagination_second_page(self):
        for i in range(num_by_page):
            art = Article.objects.create(word="zextra%02d" % i)
            ArticleSemanticField.objects.create(article=art, field=self.animals)
        response = self.c.get("/ontology/%s/2" % self.animals.id)
        self.assertEqual(200, response.status_code)
        self.assertEqual(2, response.context["page_obj"].number)
        self.assertTrue(response.context["page_obj"].object_list)

    def test_see_also_without_markup_inherits_target_field(self):
        self.assertFalse(self.see_also.semantic_assignments.exists())
        content = search_by_semantic_field(self.animals.id, 1)
        words = [a.word for a in content.page_obj.object_list]
        self.assertIn("aah", words)
        flax_words = [
            a.word
            for a in search_by_semantic_field(self.flax.id, 1).page_obj.object_list
        ]
        self.assertEqual(["muu"], flax_words)

    def test_marked_referrer_does_not_inherit_another_field(self):
        # aiga (animals) → muu (flax): outgoing from animals must not pull muu.
        # muu already has its own field, so it also must not inherit animals.
        content = search_by_semantic_field(self.animals.id, 1)
        words = [a.word for a in content.page_obj.object_list]
        self.assertNotIn("muu", words)
