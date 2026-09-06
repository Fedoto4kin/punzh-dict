"""Write cleaned rus_word lists (backlog §2)."""

from django.contrib.postgres.search import SearchVector
from django.db import transaction

from dict.helpers.rus_word import dedupe_canonical_rus_words
from dict.models import ArticleIndexTranslate


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


def apply_from_results(results):
    """
    Apply {article_id_str: {after: [...]}} from clean_translations json.
    Returns n_applied.
    """
    n = 0
    for key, rec in results.items():
        after = rec.get("after")
        if not isinstance(after, list):
            continue
        apply_translations(int(key), after)
        n += 1
    return n
