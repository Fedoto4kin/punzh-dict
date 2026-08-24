from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from ..admin import ArticleLinkReverseInline
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
        self.assertIn(self.source.word, reverse_html)
        self.assertNotIn("add-row", reverse_html)
