"""Backfill ArticleIndexTranslate.rus_lemmas from rus_word (P3)."""

from django.core.management.base import BaseCommand

from dict.helpers.rus_morph import lemmas_of_phrase
from dict.models import ArticleIndexTranslate


class Command(BaseCommand):
    help = (
        "Пересчитать rus_lemmas для всех (или --article-id) строк "
        "ArticleIndexTranslate. Идемпотентно."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--article-id",
            type=int,
            action="append",
            dest="article_ids",
            help="Ограничить статьёй (можно несколько раз).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Размер батча iterator (по умолчанию 500).",
        )

    def handle(self, *args, **options):
        qs = ArticleIndexTranslate.objects.all().order_by("pk")
        article_ids = options.get("article_ids")
        if article_ids:
            qs = qs.filter(article_id__in=article_ids)

        batch_size = options["batch_size"]
        updated = 0
        for row in qs.iterator(chunk_size=batch_size):
            lemmas = lemmas_of_phrase(row.rus_word or "")
            if list(row.rus_lemmas or []) == lemmas:
                continue
            ArticleIndexTranslate.objects.filter(pk=row.pk).update(rus_lemmas=lemmas)
            updated += 1
            if updated % 1000 == 0:
                self.stdout.write(f"updated {updated}…")

        total = qs.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"rebuild_translate_lemmas: {updated} updated / {total} rows"
            )
        )
