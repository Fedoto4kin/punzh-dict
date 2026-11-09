from django.test import Client, TestCase

from dict.models import Article, KRL_ABC


class EndpointTestCase(TestCase):
    # todo: limited fixtures
    # fixtures = ['articles.json',]
    c = Client()

    def test_pointer(self):
        for letter in KRL_ABC:
            response = self.c.get("/" + letter + "/1")
            self.assertEqual(200, response.status_code)

    def test_pointer_with_articles(self):
        # Empty letter pages never call normalization(); a real row must.
        Article.objects.create(
            word="aiga", first_letter="A", article_html="<b>aiga</b>"
        )
        response = self.c.get("/A/")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "aiga")

    def test_search(self):
        response = self.c.get("/search/aiga")
        self.assertEqual(200, response.status_code)

    # todo: test tags
