from django.test import TestCase

from ..models import Article, ArticleIndexTag, Tag
from ..search import search_by_tags_smart


# DB-backed tests for tag search after the move onto ArticleIndexTag.
# AND between groups, OR within a group. Pometы live in ArticleIndexTag
# (populated here directly, as the admin would).


class TagSearchTestCase(TestCase):
    def setUp(self):
        # tags: two geo (type1), two ling (type2), one pomета (type3)
        self.g1 = Tag.objects.create(tag="g1", name="Гео 1", type=1)
        self.g2 = Tag.objects.create(tag="g2", name="Гео 2", type=1)
        self.l1 = Tag.objects.create(tag="l1", name="Линг 1", type=2)
        self.l2 = Tag.objects.create(tag="l2", name="Линг 2", type=2)
        self.t1 = Tag.objects.create(tag="t1", name="Помета 1", type=3)

        # articles and their pometы
        self.a = Article.objects.create(word="art_a")  # l1
        self.b = Article.objects.create(word="art_b")  # l1, g1
        self.c = Article.objects.create(word="art_c")  # l2, g1
        self.d = Article.objects.create(word="art_d")  # l1, t1
        self.e = Article.objects.create(word="art_e")  # g2

        links = [
            (self.a, self.l1),
            (self.b, self.l1),
            (self.b, self.g1),
            (self.c, self.l2),
            (self.c, self.g1),
            (self.d, self.l1),
            (self.d, self.t1),
            (self.e, self.g2),
        ]
        for art, tag in links:
            ArticleIndexTag.objects.create(article=art, tag=tag)

    def _words(self, content):
        return {a.word for a in content.page_obj.object_list}

    def test_single_tag_single_group(self):
        content = search_by_tags_smart(
            by_geo=[],
            by_tags=[],
            by_ling=[self.l1.id],
            by_dialect=[],
            by_other=[],
            page=1,
        )
        self.assertEqual({"art_a", "art_b", "art_d"}, self._words(content))

    def test_or_within_group(self):
        content = search_by_tags_smart(
            by_geo=[],
            by_tags=[],
            by_ling=[self.l1.id, self.l2.id],
            by_dialect=[],
            by_other=[],
            page=1,
        )
        self.assertEqual({"art_a", "art_b", "art_c", "art_d"}, self._words(content))

    def test_and_between_groups(self):
        content = search_by_tags_smart(
            by_geo=[self.g1.id],
            by_tags=[],
            by_ling=[self.l1.id],
            by_dialect=[],
            by_other=[],
            page=1,
        )
        self.assertEqual({"art_b"}, self._words(content))

    def test_and_between_groups_empty(self):
        content = search_by_tags_smart(
            by_geo=[self.g2.id],
            by_tags=[],
            by_ling=[self.l1.id],
            by_dialect=[],
            by_other=[],
            page=1,
        )
        self.assertEqual(set(), self._words(content))

    def test_three_conditions_empty(self):
        # l1 & g1 & t1: art_b has l1,g1 but not t1; art_d has l1,t1 but not g1.
        content = search_by_tags_smart(
            by_geo=[self.g1.id],
            by_tags=[self.t1.id],
            by_ling=[self.l1.id],
            by_dialect=[],
            by_other=[],
            page=1,
        )
        self.assertEqual(set(), self._words(content))

    def test_pometa_group(self):
        content = search_by_tags_smart(
            by_geo=[],
            by_tags=[self.t1.id],
            by_ling=[],
            by_dialect=[],
            by_other=[],
            page=1,
        )
        self.assertEqual({"art_d"}, self._words(content))
