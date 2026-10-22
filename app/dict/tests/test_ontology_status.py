from django.test import TestCase

from dict.ai.ontology_status import (
    BUCKET_MARKED,
    BUCKET_PENDING,
    BUCKET_SKIP,
    filter_ontology_bucket,
    has_classify_material,
    ontology_admin_bucket,
)
from dict.models import (
    Article,
    ArticleAddition,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleKeyword,
    ArticleLink,
    ArticleSemanticField,
    SemanticField,
    Tag,
)


def _pos(tag_code, name):
    return Tag.objects.create(tag=tag_code, name=name, type=2)


class OntologyStatusHelpersTestCase(TestCase):
    def test_has_material_from_translation(self):
        art = Article.objects.create(word="kissa")
        ArticleIndexTranslate.objects.create(article=art, rus_word="кошка")
        self.assertTrue(has_classify_material(art))

    def test_has_material_from_illustration_html(self):
        art = Article.objects.create(
            word="seeplus",
            article_html="<i>см.</i> foo; лиса бежит по полю",
        )
        self.assertTrue(has_classify_material(art))

    def test_no_material_pure_see(self):
        art = Article.objects.create(word="seestub", article_html="<i>см.</i> lemma")
        self.assertFalse(has_classify_material(art))

    def test_no_material_see_with_dialect_label_vsg(self):
        # Real stub pattern (id 11050): verb + всг. + см. — «всг» is a помета.
        art = Article.objects.create(
            word="arbawttia",
            article_html="<b>arbawtti̮a</b> <i>v</i> <i>всг.</i> <i>см.</i> arvawttua",
        )
        ArticleIndexTag.objects.create(article=art, tag=_pos("v", "глагол"))
        self.assertFalse(has_classify_material(art))
        self.assertEqual(ontology_admin_bucket(art), BUCKET_SKIP)

    def test_pure_see_with_leftover_translation_is_skip(self):
        # Real stub (id 22979): el’ämä → см. eländä, but index still has «жизнь».
        target = Article.objects.create(word="elandia")
        art = Article.objects.create(
            word="elama",
            article_html="<b>el’ämä</b> <i>s</i> <i>см.</i> eländä",
        )
        ArticleIndexTag.objects.create(article=art, tag=_pos("s", "существительное"))
        ArticleIndexTranslate.objects.create(article=art, rus_word="жизнь")
        ArticleLink.objects.create(
            from_article=art, to_article=target, kind=ArticleLink.KIND_SEE
        )
        self.assertFalse(has_classify_material(art))
        self.assertEqual(ontology_admin_bucket(art), BUCKET_SKIP)

    def test_see_with_russian_illustration_stays_pending(self):
        target = Article.objects.create(word="arvata")
        art = Article.objects.create(
            word="arbata",
            article_html=(
                "<b>arba||ta</b> <i>v</i> <i>см.</i> arvata; "
                "я угадал, кто был у вас?"
            ),
        )
        ArticleIndexTag.objects.create(article=art, tag=_pos("v", "глагол"))
        ArticleLink.objects.create(
            from_article=art, to_article=target, kind=ArticleLink.KIND_SEE
        )
        self.assertTrue(has_classify_material(art))
        self.assertEqual(ontology_admin_bucket(art), BUCKET_PENDING)

    def test_has_material_from_addition(self):
        art = Article.objects.create(word="addonly", article_html="")
        ArticleAddition.objects.create(article=art, article_html="рыба в озере")
        self.assertTrue(has_classify_material(art))

    def test_buckets_partition(self):
        field = SemanticField.objects.create(name="животные", sorting=1)
        marked = Article.objects.create(word="marked")
        ArticleSemanticField.objects.create(article=marked, field=field)

        pending = Article.objects.create(word="pending")
        ArticleIndexTranslate.objects.create(article=pending, rus_word="хлеб")

        nofield_kw = Article.objects.create(word="nofield")
        ArticleKeyword.objects.create(article=nofield_kw, word="частица")

        service = Article.objects.create(word="ja")
        ArticleIndexTag.objects.create(article=service, tag=_pos("particl", "частица"))
        ArticleIndexTranslate.objects.create(article=service, rus_word="и")

        adverb = Article.objects.create(word="hyvin")
        ArticleIndexTag.objects.create(article=adverb, tag=_pos("adv", "наречие"))
        ArticleIndexTranslate.objects.create(article=adverb, rus_word="хорошо")

        numeral = Article.objects.create(word="kaksi")
        ArticleIndexTag.objects.create(article=numeral, tag=_pos("num", "числительное"))
        ArticleIndexTranslate.objects.create(article=numeral, rus_word="два")

        noun = Article.objects.create(word="talo")
        ArticleIndexTag.objects.create(article=noun, tag=_pos("s", "существительное"))
        ArticleIndexTranslate.objects.create(article=noun, rus_word="дом")

        empty = Article.objects.create(word="empty", article_html="<i>см.</i> x")

        self.assertEqual(ontology_admin_bucket(marked), BUCKET_MARKED)
        self.assertEqual(ontology_admin_bucket(pending), BUCKET_PENDING)
        self.assertEqual(ontology_admin_bucket(noun), BUCKET_PENDING)
        self.assertEqual(ontology_admin_bucket(nofield_kw), BUCKET_SKIP)
        self.assertEqual(ontology_admin_bucket(service), BUCKET_SKIP)
        self.assertEqual(ontology_admin_bucket(adverb), BUCKET_SKIP)
        self.assertEqual(ontology_admin_bucket(numeral), BUCKET_SKIP)
        self.assertEqual(ontology_admin_bucket(empty), BUCKET_SKIP)


class OntologyStatusFilterTestCase(TestCase):
    def setUp(self):
        self.field = SemanticField.objects.create(name="еда", sorting=1)
        self.marked = Article.objects.create(word="kissa")
        ArticleSemanticField.objects.create(article=self.marked, field=self.field)

        self.pending = Article.objects.create(word="leipa")
        ArticleIndexTranslate.objects.create(article=self.pending, rus_word="хлеб")

        self.pending_ill = Article.objects.create(
            word="illust",
            article_html="<i>см.</i> x; бежит лиса",
        )

        self.skip_kw = Article.objects.create(word="nofield")
        ArticleKeyword.objects.create(article=self.skip_kw, word="см")

        self.skip_empty = Article.objects.create(
            word="seestub", article_html="<i>см.</i> lemma"
        )

        self.skip_service = Article.objects.create(word="noin")
        ArticleIndexTag.objects.create(
            article=self.skip_service, tag=_pos("prep", "предлог")
        )
        ArticleIndexTranslate.objects.create(article=self.skip_service, rus_word="в")

        self.skip_adv = Article.objects.create(word="hyvin")
        ArticleIndexTag.objects.create(
            article=self.skip_adv, tag=_pos("adv", "наречие")
        )
        ArticleIndexTranslate.objects.create(article=self.skip_adv, rus_word="хорошо")

        self.pending_noun = Article.objects.create(word="talo")
        ArticleIndexTag.objects.create(
            article=self.pending_noun, tag=_pos("s", "существительное")
        )
        ArticleIndexTranslate.objects.create(article=self.pending_noun, rus_word="дом")

    def _ids(self, bucket):
        return set(
            filter_ontology_bucket(Article.objects.all(), bucket).values_list(
                "pk", flat=True
            )
        )

    def test_marked(self):
        self.assertEqual(self._ids(BUCKET_MARKED), {self.marked.pk})

    def test_pending(self):
        self.assertEqual(
            self._ids(BUCKET_PENDING),
            {self.pending.pk, self.pending_ill.pk, self.pending_noun.pk},
        )

    def test_skip(self):
        self.assertEqual(
            self._ids(BUCKET_SKIP),
            {
                self.skip_kw.pk,
                self.skip_empty.pk,
                self.skip_service.pk,
                self.skip_adv.pk,
            },
        )

    def test_partition_covers_all_without_overlap(self):
        all_ids = set(Article.objects.values_list("pk", flat=True))
        marked = self._ids(BUCKET_MARKED)
        pending = self._ids(BUCKET_PENDING)
        skip = self._ids(BUCKET_SKIP)
        self.assertEqual(marked | pending | skip, all_ids)
        self.assertFalse(marked & pending)
        self.assertFalse(marked & skip)
        self.assertFalse(pending & skip)
