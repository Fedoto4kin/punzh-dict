"""Semantic-field ontology listing and counts."""

from collections import defaultdict

from django.db.models import Count, Prefetch, Q

from dict.helpers import build_pagination_hints
from dict.models import Article, ArticleLink, ArticleSemanticField, SemanticField

from .common import Content, num_by_page, sort_and_paginate
from .krl import tag_filtered_ids_and_facets


def _referrers_inheriting_field(classified, referrers_by_target, fields_by_article):
    """
    See/deriv referrers that belong in this field via a target already in it.

    Included when at least one such target already has every field the
    referrer has (no markup is a subset). A field the target lacks blocks
    inheritance from that target only; other targets are checked on their own.
    """
    inherited = set()
    for target_id in classified:
        target_fields = fields_by_article.get(target_id)
        if not target_fields:
            continue
        for referrer_id in referrers_by_target.get(target_id, ()):
            referrer_fields = fields_by_article.get(referrer_id, frozenset())
            if referrer_fields <= target_fields:
                inherited.add(referrer_id)
    return inherited


def article_ids_for_semantic_field(field_id, include_all=True, include_referrers=True):
    """
    Articles in a semantic field, plus «см.» / «от» referrers when include_all
    and include_referrers.

    Lemmas classified into the field are the core set. A referrer inherits
    this field at read time when it points at one of those lemmas and every
    field it already has is also on that target. Same kinds as expand_by_links
    in Russian search, but one-way: outgoing links are not followed.
    The field is not copied onto ArticleSemanticField.

    include_all=False — only assignments with from_translation=True (no
    illustration-only fields, no referrer inheritance).
    include_referrers=False — classified assignments only (no см./от pull-in).
    """
    if not include_all:
        return set(
            ArticleSemanticField.objects.filter(
                field_id=field_id, from_translation=True
            ).values_list("article_id", flat=True)
        )
    classified = set(
        ArticleSemanticField.objects.filter(field_id=field_id).values_list(
            "article_id", flat=True
        )
    )
    if not classified or not include_referrers:
        return classified
    referrers_by_target = defaultdict(set)
    referrer_ids = set()
    for from_id, to_id in ArticleLink.objects.filter(
        to_article_id__in=classified,
        kind__in=ArticleLink.KINDS_LISTING,
    ).values_list("from_article_id", "to_article_id"):
        referrers_by_target[to_id].add(from_id)
        referrer_ids.add(from_id)
    if not referrer_ids:
        return classified
    fields_by_article = defaultdict(set)
    for fid, aid in ArticleSemanticField.objects.filter(
        article_id__in=classified | referrer_ids
    ).values_list("field_id", "article_id"):
        fields_by_article[aid].add(fid)
    return classified | _referrers_inheriting_field(
        classified, referrers_by_target, fields_by_article
    )


def semantic_fields_with_counts():
    """
    Attach badge counts to each SemanticField:
    translation_count — articles with from_translation=True (x);
    article_count — full listing size, same referrer rule as
    article_ids_for_semantic_field (y). Templates show x/y.

    Computed in a few queries for all fields (not N×article_ids_for_semantic_field).
    """
    fields = list(SemanticField.objects.all())
    if not fields:
        return fields

    translation_counts = {
        row["field_id"]: row["n"]
        for row in ArticleSemanticField.objects.filter(from_translation=True)
        .values("field_id")
        .annotate(n=Count("article_id", distinct=True))
    }

    classified_by_field = defaultdict(set)
    fields_by_article = defaultdict(set)
    for field_id, article_id in ArticleSemanticField.objects.values_list(
        "field_id", "article_id"
    ):
        classified_by_field[field_id].add(article_id)
        fields_by_article[article_id].add(field_id)

    all_classified = set()
    for ids in classified_by_field.values():
        all_classified |= ids

    referrers_by_target = defaultdict(set)
    if all_classified:
        for from_id, to_id in ArticleLink.objects.filter(
            to_article_id__in=all_classified,
            kind__in=ArticleLink.KINDS_LISTING,
        ).values_list("from_article_id", "to_article_id"):
            referrers_by_target[to_id].add(from_id)

    for field in fields:
        field.translation_count = translation_counts.get(field.pk, 0)
        classified = classified_by_field.get(field.pk, set())
        inherited = _referrers_inheriting_field(
            classified, referrers_by_target, fields_by_article
        )
        field.article_count = len(classified | inherited)
    return fields


def search_by_semantic_field(
    field_id, page, tag_ids=None, phrase=False, include_all=False
):
    """
    Articles in a semantic field, optional ?t= / ?ph= / ?all=1.

    Default include_all=False — only from_translation assignments.
    """
    include_all = bool(include_all)
    filtered_ids, groups, phrase_filter, t_query = tag_filtered_ids_and_facets(
        article_ids_for_semantic_field(field_id, include_all=include_all),
        tag_ids,
        phrase,
        include_all=include_all,
    )
    articles = Article.objects.filter(pk__in=filtered_ids)
    page_obj, sorted_articles = sort_and_paginate(articles, page)
    trigrams_dict = build_pagination_hints(sorted_articles, num_by_page)
    return Content(
        page_obj=page_obj,
        trigrams_dict=trigrams_dict,
        tag_filter_groups=groups or [],
        phrase_filter=phrase_filter,
        t_query=t_query,
    )
