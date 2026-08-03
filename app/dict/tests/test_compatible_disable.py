from django.test import TestCase

from ..models import Article, ArticleIndexTag, Tag
from ..search import article_ids_by_tags, compatible_disable


# DB-backed tests for the tag-compatibility endpoint logic.
# compatible_disable(selected) -> tag ids to disable. A candidate tag of group
# G is available iff (selection WITHOUT group G) AND that tag yields >=1 article
# — a same-group tag still has to intersect the OTHER groups (AND is priority
# over the within-group OR).


class CompatibleDisableTestCase(TestCase):
    def setUp(self):
        self.g1 = Tag.objects.create(tag="g1", name="Гео 1", type=1)
        self.g2 = Tag.objects.create(tag="g2", name="Гео 2", type=1)
        self.l1 = Tag.objects.create(tag="l1", name="Линг 1", type=2)
        self.l2 = Tag.objects.create(tag="l2", name="Линг 2", type=2)
        self.t1 = Tag.objects.create(tag="t1", name="Помета 1", type=3)

        self.a = Article.objects.create(word="art_a")  # l1
        self.b = Article.objects.create(word="art_b")  # l1, g1
        self.c = Article.objects.create(word="art_c")  # l2, g1
        self.d = Article.objects.create(word="art_d")  # l1, t1
        self.e = Article.objects.create(word="art_e")  # g2

        for art, tag in [
            (self.a, self.l1),
            (self.b, self.l1),
            (self.b, self.g1),
            (self.c, self.l2),
            (self.c, self.g1),
            (self.d, self.l1),
            (self.d, self.t1),
            (self.e, self.g2),
        ]:
            ArticleIndexTag.objects.create(article=art, tag=tag)

    def test_single_ling(self):
        # l1 -> A,B,D; ни одна не g2 -> гасим g2. l2 (своя группа) не гасится:
        # выбор без группы2 = все статьи, l2 встречается (C) -> доступна.
        self.assertEqual({self.g2.id}, set(compatible_disable([self.l1.id])))

    def test_single_geo(self):
        self.assertEqual({self.t1.id}, set(compatible_disable([self.g1.id])))

    def test_narrow_pometa(self):
        self.assertEqual(
            {self.g1.id, self.g2.id, self.l2.id},
            set(compatible_disable([self.t1.id])),
        )

    def test_two_groups_disables_incompatible_same_and_other(self):
        # l1 & g1 -> {B}. t1: l1&g1&t1 пусто -> гасим. g2: выбор без группы1 =
        # [l1] -> {A,B,D}, g2 только в E -> пусто -> ГАСИМ g2 тоже.
        # (Старая логика ошибочно оставляла g2 доступной — это и был баг.)
        self.assertEqual(
            {self.t1.id, self.g2.id},
            set(compatible_disable([self.l1.id, self.g1.id])),
        )

    def test_single_geo_g2(self):
        self.assertEqual(
            {self.l1.id, self.l2.id, self.t1.id},
            set(compatible_disable([self.g2.id])),
        )

    def test_single_ling_l2(self):
        self.assertEqual(
            {self.g2.id, self.t1.id},
            set(compatible_disable([self.l2.id])),
        )

    def test_own_group_disabled_when_incompatible_with_others(self):
        # Ключевой случай бага: выбрана своя группа + чужая; второй тег своей
        # группы гаснет, если несовместим с чужой. Здесь после [g1] выбор
        # второго geo g2: выбор без группы1 = [] -> все статьи, но проверяем
        # именно комбинацию через инвариант ниже.
        disable = set(compatible_disable([self.l1.id, self.g1.id]))
        # g2 в disable, т.к. l1 AND g2 пусто
        self.assertIn(self.g2.id, disable)

    def test_invariant_disabled_yield_zero_with_others(self):
        # погашенная k: (выбор без группы k) AND k = 0
        selected = [self.l1.id, self.g1.id]
        type_by_id = dict(Tag.objects.values_list("id", "type"))
        for tid in compatible_disable(selected):
            g = type_by_id[tid]
            sel_wo = [t for t in selected if type_by_id[t] != g]
            base = article_ids_by_tags(sel_wo)
            with_k = article_ids_by_tags(sel_wo + [tid])
            self.assertEqual(
                0,
                len(with_k),
                msg=f"tag {tid} disabled but (selection w/o its group) + it is non-empty",
            )

    def test_empty_selection_disables_nothing(self):
        self.assertEqual([], compatible_disable([]))
