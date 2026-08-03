from django.core.management.base import BaseCommand
from django.db import transaction

from dict.models import Article, ArticleIndexTag, Tag


class Command(BaseCommand):
    help = (
        "Разовая пересборка ArticleIndexTag из article_html (и дополнений). "
        "Матчинг повторяет search_by_tags_smart: типы 1-4 через <i>tag</i>, "
        "тип 5 голым текстом. Идемпотентна: очищает индекс и строит заново."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch", type=int, default=500,
            help="Сколько связей накапливать перед bulk_create (по умолчанию 500).",
        )

    def handle(self, *args, **options):
        batch_size = options["batch"]

        # Справочник тегов — один раз. Заранее готовим "иглу" для поиска.
        needles = []  # (tag_id, needle_substring)
        for tid, value, ttype in Tag.objects.values_list("id", "tag", "type"):
            if not value:
                continue
            needle = value if ttype == 5 else "<i>" + value + "</i>"
            needles.append((tid, needle))
        self.stdout.write(f"Тегов в справочнике: {len(needles)}")

        with transaction.atomic():
            deleted, _ = ArticleIndexTag.objects.all().delete()
            self.stdout.write(f"Удалено старых связей: {deleted}")

            buffer = []
            n_articles = 0
            n_links = 0
            qs = Article.objects.prefetch_related("additions").iterator(chunk_size=200)
            for article in qs:
                # HTML статьи + всех её дополнений
                blobs = [article.article_html or ""]
                for add in article.additions.all():
                    blobs.append(add.article_html or "")

                for tid, needle in needles:
                    hit = False
                    for b in blobs:
                        if needle in b:
                            hit = True
                            break
                    if hit:
                        buffer.append(
                            ArticleIndexTag(article_id=article.id, tag_id=tid)
                        )
                        n_links += 1

                n_articles += 1
                if len(buffer) >= batch_size:
                    ArticleIndexTag.objects.bulk_create(buffer)
                    buffer = []
                if n_articles % 1000 == 0:
                    self.stdout.write(f"  обработано статей: {n_articles}")

            if buffer:
                ArticleIndexTag.objects.bulk_create(buffer)

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово. Статей: {n_articles}, связей создано: {n_links}."
            )
        )
