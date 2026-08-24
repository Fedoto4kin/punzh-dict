from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from ..admin import ArticleLinkReverseInline
from ..helpers import normalization
from ..models import Article, ArticleLink


class ArticleLinkReverseInlineTestCase(TestCase):
    def setUp(self):
        self.inline = ArticleLinkReverseInline(Article, AdminSite())
        self.factory = RequestFactory()
        self.user = User.objects.create_superuser("admin", "a@example.com", "x")
        self.target = Article.objects.create(word="kohde")
        self.source = Article.objects.create(word="lahde")
        ArticleLink.objects.create(from_article=self.source, to_article=self.target)

    def test_cannot_add_incoming_link_from_target_article(self):
        request = self.factory.get("/admin/dict/article/")
        request.user = self.user
        self.assertFalse(self.inline.has_add_permission(request, self.target))

    def test_change_form_has_no_add_row_in_reverse_inline(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/admin/dict/article/{self.target.pk}/change/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        parts = html.split('id="links_to-group"', 1)
        self.assertEqual(len(parts), 2)
        reverse_html = parts[1].split("</fieldset>", 1)[0]
        self.assertIn("На эту статью указывают", reverse_html)
        self.assertIn(f">{normalization(self.source.word)}</a>", reverse_html)
        self.assertNotIn("add-row", reverse_html)

    def test_incoming_source_uses_normalized_orthography(self):
        target = Article.objects.create(word="vuag||ie")
        source = Article.objects.create(word="riw||gu, ~gun’e")
        ArticleLink.objects.create(from_article=source, to_article=target)
        self.client.force_login(self.user)
        response = self.client.get(f"/admin/dict/article/{target.pk}/change/")
        self.assertEqual(response.status_code, 200)
        reverse_html = (
            response.content.decode().split('id="links_to-group"', 1)[1].split(
                "</fieldset>", 1
            )[0]
        )
        self.assertIn(">riugu, riugune</a>", reverse_html)

    def test_both_link_inlines_hide_original_str_overlay(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/admin/dict/article/{self.source.pk}/change/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("#links_from-group .tabular td.original p", html)
        self.assertIn("#links_to-group .tabular td.original p", html)
        from_html = html.split('id="links_from-group"', 1)[1].split("</fieldset>", 1)[0]
        self.assertIn("admin-autocomplete", from_html)
        self.assertIn("Смотрите также", from_html)
