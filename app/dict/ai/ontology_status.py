"""
Admin ontology queue buckets: marked / pending / skip.

Ontology fields are for content lemmas (noun / verb / adjective). Other POS
(adverb, numeral, pronoun, conjunction, …) go to «разметка не нужна».
Verb aspect/voice flavors alone (mom, caus, …) do not count as content.
Negation verbs (HTML «negat» or see→negat) are skip.
Pure «см.» stubs (even with a leftover translation index row) are skip.
"""

from __future__ import annotations

import re

from django.db.models import Exists, OuterRef, Q

from dict.ai.prompts import article_html_blobs, build_article_input, cyrillic_from_html
from dict.models import (
    ArticleAddition,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleKeyword,
    ArticleLink,
    ArticleSemanticField,
)

# Head POS codes (type=2) that can carry a thematic field.
# Secondary flavors (mom, caus, freq, …) alone do not qualify.
CONTENT_POS_TAGS = frozenset({"s", "v", "a"})

# Cyrillic spans shorter than this are ignored as illustration material.
_MIN_ILLUSTRATION_LEN = 4
# PostgreSQL approx. for changelist (labels like «всг» are 3 letters).
_CYR_HTML_RE = rf"[а-яёА-ЯЁ]{{{_MIN_ILLUSTRATION_LEN},}}"
# Dictionary label <i>negat</i> (negation auxiliary / paradigm).
_NEGAT_LABEL_RE = re.compile(r"<i[^>]*>\s*negat\b", re.I)
_NEGAT_HTML_RE = r"<i[^>]*>\s*negat"

BUCKET_MARKED = "marked"
BUCKET_PENDING = "pending"
BUCKET_SKIP = "skip"

_POS_TYPE = 2


def is_ontology_unsupported_pos(article) -> bool:
    """
    True if the article has POS tags (type=2) but none are content (s/v/a).

    No POS tags → False (allow pending for newly added words).
    """
    codes = set(
        article.articleindextag_set.filter(tag__type=_POS_TYPE).values_list(
            "tag__tag", flat=True
        )
    )
    if not codes:
        return False
    return codes.isdisjoint(CONTENT_POS_TAGS)


def is_service_pos_article(article) -> bool:
    """Back-compat alias."""
    return is_ontology_unsupported_pos(article)


def is_negation_article(article) -> bool:
    """
    Negation auxiliary / paradigm form: HTML label «negat», or «см.» to such.
    """
    for blob in article_html_blobs(article):
        if _NEGAT_LABEL_RE.search(blob or ""):
            return True
    targets = ArticleLink.objects.filter(
        from_article_id=article.pk, kind=ArticleLink.KIND_SEE
    ).select_related("to_article")
    for link in targets:
        target = link.to_article
        if target is None:
            continue
        for blob in article_html_blobs(target):
            if _NEGAT_LABEL_RE.search(blob or ""):
                return True
    return False


def is_pure_see_stub(article) -> bool:
    """
    Outgoing «см.» and no real Russian illustration in HTML.

    Leftover ArticleIndexTranslate rows (e.g. el’ämä → «жизнь») do not
    make a pure cross-ref eligible for the pending queue.
    """
    if not ArticleLink.objects.filter(
        from_article_id=article.pk, kind=ArticleLink.KIND_SEE
    ).exists():
        return False
    for blob in article_html_blobs(article):
        for span in cyrillic_from_html(blob):
            if len(span) >= _MIN_ILLUSTRATION_LEN:
                return False
    return True


def has_classify_material(article) -> bool:
    """
    Russian material usable for ontology classify.

    Real HTML illustrations count. Indexed translations count only when the
    article is not a pure «см.» stub. Dictionary labels in <i> are not
    illustrations (see prompts.strip_dict_label_italics).
    """
    payload = build_article_input(article)
    if any(len(span) >= _MIN_ILLUSTRATION_LEN for span in payload["illustrations_ru"]):
        return True
    if not payload["translations"]:
        return False
    return not is_pure_see_stub(article)


def ontology_admin_bucket(article) -> str:
    """
    Partition for admin filter (mutually exclusive):

    - marked: has at least one semantic field
    - pending: no fields, no keywords, content-or-unknown POS, has material
    - skip: no fields, and not pending
    """
    if article.semantic_assignments.exists():
        return BUCKET_MARKED
    has_kw = ArticleKeyword.objects.filter(article_id=article.pk).exists()
    if (
        has_kw
        or is_ontology_unsupported_pos(article)
        or is_negation_article(article)
        or not has_classify_material(article)
    ):
        return BUCKET_SKIP
    return BUCKET_PENDING


def _has_content_pos_exists():
    return Exists(
        ArticleIndexTag.objects.filter(
            article_id=OuterRef("pk"),
            tag__type=_POS_TYPE,
            tag__tag__in=CONTENT_POS_TAGS,
        )
    )


def _has_any_pos_exists():
    return Exists(
        ArticleIndexTag.objects.filter(
            article_id=OuterRef("pk"),
            tag__type=_POS_TYPE,
        )
    )


def _unsupported_pos_q():
    """Has POS markup, but no content POS (adv/num/pron/conj/…)."""
    return _has_any_pos_exists() & ~_has_content_pos_exists()


def _negation_q():
    """Own HTML «negat» or see-link to an article with «negat»."""
    own_html = Q(article_html__iregex=_NEGAT_HTML_RE)
    own_add = Exists(
        ArticleAddition.objects.filter(
            article_id=OuterRef("pk"),
            article_html__iregex=_NEGAT_HTML_RE,
        )
    )
    see_target = Exists(
        ArticleLink.objects.filter(
            from_article_id=OuterRef("pk"),
            kind=ArticleLink.KIND_SEE,
            to_article__article_html__iregex=_NEGAT_HTML_RE,
        )
    )
    see_target_add = Exists(
        ArticleLink.objects.filter(
            from_article_id=OuterRef("pk"),
            kind=ArticleLink.KIND_SEE,
            to_article__additions__article_html__iregex=_NEGAT_HTML_RE,
        )
    )
    return own_html | own_add | see_target | see_target_add


def _has_translation_exists():
    return Exists(
        ArticleIndexTranslate.objects.filter(article_id=OuterRef("pk"))
        .exclude(rus_word__isnull=True)
        .exclude(rus_word="")
    )


def _has_see_link_exists():
    return Exists(
        ArticleLink.objects.filter(
            from_article_id=OuterRef("pk"),
            kind=ArticleLink.KIND_SEE,
        )
    )


def _has_cyrillic_html_q():
    has_cyr_add = Exists(
        ArticleAddition.objects.filter(
            article_id=OuterRef("pk"),
            article_html__regex=_CYR_HTML_RE,
        )
    )
    return Q(article_html__regex=_CYR_HTML_RE) | has_cyr_add


def _has_material_q():
    """
    Illustrations (Cyrillic in HTML) or translations on non-see stubs.

    Approx. pure see: outgoing see + no Cyrillic ≥4 in HTML → translation
    alone does not count (matches is_pure_see_stub).
    """
    has_cyr = _has_cyrillic_html_q()
    has_tr = _has_translation_exists()
    has_see = _has_see_link_exists()
    return has_cyr | (has_tr & ~has_see)


def _no_fields_q(queryset):
    if "_ontology_field_count" in queryset.query.annotations:
        return Q(_ontology_field_count=0)
    return ~Exists(ArticleSemanticField.objects.filter(article_id=OuterRef("pk")))


def _no_keywords_q(queryset):
    if "_ontology_kw_count" in queryset.query.annotations:
        return Q(_ontology_kw_count=0)
    return ~Exists(ArticleKeyword.objects.filter(article_id=OuterRef("pk")))


def filter_ontology_bucket(queryset, bucket: str):
    """
    Apply admin ontology bucket to an Article queryset.

    Prefers annotations _ontology_field_count / _ontology_kw_count from
    ArticleAdm.get_queryset when present.
    """
    unsupported_pos = _unsupported_pos_q()
    negation = _negation_q()
    has_material = _has_material_q()
    annotated = "_ontology_field_count" in queryset.query.annotations

    if bucket == BUCKET_MARKED:
        if annotated:
            return queryset.filter(_ontology_field_count__gt=0)
        return queryset.filter(
            Exists(ArticleSemanticField.objects.filter(article_id=OuterRef("pk")))
        )

    if bucket == BUCKET_PENDING:
        return queryset.filter(
            _no_fields_q(queryset),
            _no_keywords_q(queryset),
            ~unsupported_pos,
            ~negation,
            has_material,
        )

    if bucket == BUCKET_SKIP:
        if annotated:
            return queryset.filter(_ontology_field_count=0).filter(
                Q(_ontology_kw_count__gt=0) | unsupported_pos | negation | ~has_material
            )
        return queryset.filter(
            ~Exists(ArticleSemanticField.objects.filter(article_id=OuterRef("pk")))
        ).filter(
            Exists(ArticleKeyword.objects.filter(article_id=OuterRef("pk")))
            | unsupported_pos
            | negation
            | ~has_material
        )

    return queryset
