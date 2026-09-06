from django.contrib.auth.models import User
from django.test import TestCase

from ..models import Article


class ArticleHtmlEditorAdminTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "a@example.com", "x")
        self.article = Article.objects.create(
            word="kohde",
            article_html="<b>koh||de</b> <i>см.</i> lemma быстро",
        )
        self.client.force_login(self.user)

    def test_change_form_loads_codemirror_and_html_source_widget(self):
        response = self.client.get(f"/admin/dict/article/{self.article.pk}/change/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("article-html-source", html)
        self.assertIn("codemirror.min.js", html)
        self.assertIn("mode/htmlmixed/htmlmixed.min.js", html)
        self.assertIn("admin/js/article_html_editor.js", html)
        self.assertIn("admin/css/article_html_editor.css", html)
        self.assertIn("beautify-html.min.js", html)
        self.assertIn('id="id_article_html"', html)

    def test_change_form_renders_html_like_translation_browser(self):
        response = self.client.get(f"/admin/dict/article/{self.article.pk}/change/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('class="article-html-preview"', html)
        self.assertIn(".article-html-preview .text-rus", html)
        self.assertIn('class="text-rus" style="color:#0b5"', html)
        self.assertIn("быстро", html)
        self.assertIn('class="text-muted font-weight-normal"', html)
        self.assertIn('href="/search/lemma"', html)

    def test_add_form_also_uses_html_source_widget(self):
        response = self.client.get("/admin/dict/article/add/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("article-html-source", html)
        self.assertIn("codemirror.min.js", html)
