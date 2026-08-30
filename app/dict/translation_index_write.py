"""Write cleaned rus_word lists; snapshot before batch (backlog §2)."""

from datetime import datetime, timezone

from django.contrib.postgres.search import SearchVector
from django.db import transaction

from dict.helpers.rus_word import dedupe_canonical_rus_words
from dict.models import Article, ArticleIndexTranslate, ArticleIndexTranslateSnapshot


def make_batch_id():
    return datetime.now(timezone.utc).strftime("cleanup_%Y%m%dT%H%M%SZ")


def snapshot_translation_index(batch_id):
    """Copy entire ArticleIndexTranslate into snapshot table."""
    rows = list(ArticleIndexTranslate.objects.values_list("article_id", "rus_word"))
    if not rows:
        return 0
    ArticleIndexTranslateSnapshot.objects.bulk_create(
        [
            ArticleIndexTranslateSnapshot(
                batch_id=batch_id,
                article_id=aid,
                rus_word=rw,
            )
            for aid, rw in rows
        ],
        batch_size=2000,
    )
    return len(rows)


def apply_translations(article_id, words):
    """Replace article translations; refresh search_vector (bulk_create skips signals)."""
    cleaned = dedupe_canonical_rus_words(words)
    with transaction.atomic():
        ArticleIndexTranslate.objects.filter(article_id=article_id).delete()
        if cleaned:
            ArticleIndexTranslate.objects.bulk_create(
                [
                    ArticleIndexTranslate(article_id=article_id, rus_word=w)
                    for w in cleaned
                ]
            )
            ArticleIndexTranslate.objects.filter(article_id=article_id).update(
                search_vector=SearchVector("rus_word", config="simple")
            )


def apply_from_results(results, batch_id=None, *, do_snapshot=True):
    """
    Apply {article_id_str: {after: [...]}} from clean_translations json.
    Returns (batch_id, n_applied).
    """
    if batch_id is None:
        batch_id = make_batch_id()
    if do_snapshot:
        snapshot_translation_index(batch_id)
    n = 0
    for key, rec in results.items():
        after = rec.get("after")
        if not isinstance(after, list):
            continue
        apply_translations(int(key), after)
        n += 1
    return batch_id, n
