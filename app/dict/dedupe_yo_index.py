# One-off: dedupe ArticleIndexTranslate rows that differ only by ё/е.
# Dry-run by default. Run:
#   docker exec -i -w /app punzh_django python manage.py shell < dict/dedupe_yo_index.py
# Set WRITE = True to apply.

from collections import defaultdict

from django.contrib.postgres.search import SearchVector
from django.db import transaction

from dict.helpers.rus_word import canonical_rus_word
from dict.models import ArticleIndexTranslate

WRITE = False
ARTICLE_ID = None  # e.g. 12345 for pilot; None = all articles

qs = ArticleIndexTranslate.objects.all().order_by("article_id", "id")
if ARTICLE_ID:
    qs = qs.filter(article_id=ARTICLE_ID)

by_article = defaultdict(list)
for pk, article_id, rus_word in qs.values_list("id", "article_id", "rus_word"):
    by_article[article_id].append((pk, rus_word))

delete_ids = []
updates = []
duplicate_groups = 0

for article_id, rows in by_article.items():
    groups = defaultdict(list)
    for pk, rus_word in rows:
        canon = canonical_rus_word(rus_word)
        groups[canon.lower()].append((pk, rus_word, canon))

    for items in groups.values():
        if len(items) > 1:
            duplicate_groups += 1
            keep = min(items, key=lambda t: (t[1] != t[2], len(t[1]), t[0]))
            for pk, rus_word, canon in items:
                if pk == keep[0]:
                    if rus_word != canon:
                        updates.append((pk, canon))
                else:
                    delete_ids.append(pk)
        elif len(items) == 1:
            pk, rus_word, canon = items[0]
            if rus_word != canon:
                updates.append((pk, canon))

affected_articles = set()
for pk in delete_ids:
    aid = (
        ArticleIndexTranslate.objects.filter(pk=pk)
        .values_list("article_id", flat=True)
        .first()
    )
    if aid:
        affected_articles.add(aid)
for pk, _new_word in updates:
    aid = (
        ArticleIndexTranslate.objects.filter(pk=pk)
        .values_list("article_id", flat=True)
        .first()
    )
    if aid:
        affected_articles.add(aid)

print(
    f"articles={len(by_article)} duplicate_groups={duplicate_groups} "
    f"delete={len(delete_ids)} update={len(updates)}"
)

if not delete_ids and not updates:
    print("nothing to do")
elif not WRITE:
    print("dry-run; set WRITE = True to apply")
    for pk, new_word in updates[:20]:
        old = (
            ArticleIndexTranslate.objects.filter(pk=pk)
            .values_list("rus_word", flat=True)
            .first()
        )
        print(f"  update pk={pk}: {old!r} -> {new_word!r}")
    for pk in delete_ids[:20]:
        row = (
            ArticleIndexTranslate.objects.filter(pk=pk)
            .values_list("article_id", "rus_word")
            .first()
        )
        if row:
            print(f"  delete pk={pk} article={row[0]} rus_word={row[1]!r}")
else:
    with transaction.atomic():
        if delete_ids:
            ArticleIndexTranslate.objects.filter(id__in=delete_ids).delete()
        for pk, new_word in updates:
            ArticleIndexTranslate.objects.filter(pk=pk).update(rus_word=new_word)
        for article_id in affected_articles:
            ArticleIndexTranslate.objects.filter(article_id=article_id).update(
                search_vector=SearchVector("rus_word", config="simple")
            )
    print(f"done; search_vector rebuilt for {len(affected_articles)} articles")
