from django.test import Client, SimpleTestCase


class RobotsTxtTestCase(SimpleTestCase):
    def test_robots_txt_is_plain_and_not_letter_redirect(self):
        response = Client().get("/robots.txt")
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/plain; charset=utf-8", response["Content-Type"])
        body = response.content.decode("utf-8")
        self.assertIn("User-agent: PerplexityBot", body)
        self.assertIn("Crawl-delay: 10", body)
        self.assertNotIn("<html", body.lower())

    def test_trailing_slash_not_required(self):
        # CommonMiddleware must not 301 /robots.txt → /robots.txt/
        response = Client().get("/robots.txt", follow=False)
        self.assertEqual(200, response.status_code)
