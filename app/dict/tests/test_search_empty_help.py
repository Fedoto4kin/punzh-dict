"""Empty /search/ shows how-search-works help (not an empty void)."""

from django.test import Client, TestCase


class SearchEmptyHelpTestCase(TestCase):
    def setUp(self):
        self.client = Client()

    def test_empty_search_shows_help(self):
        response = self.client.get("/search/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn('id="search-help"', html)
        self.assertIn("Как работает поиск", html)
        self.assertIn("Точные результаты", html)
        self.assertIn("Расширенный поиск", html)
        # Karelian wildcards called out in the help.
        self.assertIn("<b>.</b>", html)
        self.assertIn("<b>?</b>", html)

    def test_empty_search_without_trailing_slash(self):
        response = self.client.get("/search")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Как работает поиск", response.content.decode("utf-8"))

    def test_nonempty_search_hides_help(self):
        response = self.client.get("/search/aiga")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('id="search-help"', response.content.decode("utf-8"))

    def test_home_reuses_same_search_help(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn('id="search-help"', html)
        self.assertIn("Словоформы (падежи, спряжения) обычно находятся через леммы", html)
        self.assertNotIn("словоформы пока не распознаются", html)
