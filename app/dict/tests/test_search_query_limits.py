from urllib.parse import unquote

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from dict import views


class SearchQueryLimitTests(TestCase):
    def setUp(self):
        self.client = Client()
        cache.delete("lex_search_rl:127.0.0.1")

    def test_clip_search_query_caps_length(self):
        long_q = "а" * (views.MAX_SEARCH_QUERY_LEN + 50)
        clipped = views._clip_search_query(long_q)
        self.assertEqual(len(clipped), views.MAX_SEARCH_QUERY_LEN)

    def test_search_path_clips_oversized_query(self):
        # Keep URL moderate: only slightly over the cap (very long paths → 400).
        long_q = "к" * (views.MAX_SEARCH_QUERY_LEN + 10)
        response = self.client.get(f"/search/{long_q}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["query"]), views.MAX_SEARCH_QUERY_LEN)

    def test_search_proc_clips_before_redirect(self):
        long_q = "а" * (views.MAX_SEARCH_QUERY_LEN + 20)
        response = self.client.get("/search/", {"query": long_q}, follow=False)
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(location.startswith("/search/"))
        q = unquote(location[len("/search/") :])
        self.assertEqual(len(q), views.MAX_SEARCH_QUERY_LEN)

    @override_settings(DEBUG=False)
    def test_rate_limit_blocks_after_burst_when_not_debug(self):
        key = "lex_search_rl:127.0.0.1"
        cache.set(key, views.SEARCH_RATE_LIMIT_PER_MINUTE, timeout=60)
        response = self.client.get("/search/корова")
        self.assertEqual(response.status_code, 400)
