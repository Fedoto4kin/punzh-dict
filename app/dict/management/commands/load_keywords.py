import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from dict.models import Article, ArticleKeyword


class Command(BaseCommand):
    help = (
        "Залить СЫРЬЁ ключевых слов из json классификатора (ключ 'keywords': "
        "{article_id: [word, ...]}) в ArticleKeyword. Жёстко: для статей из "
        "json удалить их keywords и создать заново. Санитария (не чистка от "
        "шума): отсечь пустые, однобуквенные, чисто-числовые. Программная "
        "чистка от стоп-слов/POS — отдельная задача этапа поиска."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Путь к json классификации.")
        parser.add_argument("--batch", type=int, default=2000)

    @staticmethod
    def _sanitize(word):
        w = (word or "").strip().lower()
        if len(w) < 2:
            return None
        if w.isdigit():
            return None
        return w

    def handle(self, *args, **options):
        path = options["file"]
        if not os.path.exists(path):
            self.stderr.write(f"Файл не найден: {path}")
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        kw_map = data.get("keywords") or {}
        if not kw_map:
            self.stderr.write("В json нет 'keywords' или пусто.")
            return
        self.stdout.write(f"Статей с keywords в json: {len(kw_map)}")

        article_ids = []
        for aid in kw_map.keys():
            try:
                article_ids.append(int(aid))
            except (TypeError, ValueError):
                continue
        existing = set(
            Article.objects.filter(id__in=article_ids).values_list("id", flat=True)
        )

        buffer = []
        n_articles = 0
        n_words = 0
        missing_articles = 0

        with transaction.atomic():
            ArticleKeyword.objects.filter(article_id__in=existing).delete()

            for aid_str, words in kw_map.items():
                try:
                    aid = int(aid_str)
                except (TypeError, ValueError):
                    continue
                if aid not in existing:
                    missing_articles += 1
                    continue
                n_articles += 1
                seen = set()  # дедуп в пределах статьи (unique_together)
                for raw in words or []:
                    w = self._sanitize(raw)
                    if not w or w in seen:
                        continue
                    seen.add(w)
                    buffer.append(ArticleKeyword(article_id=aid, word=w))
                    n_words += 1
                    if len(buffer) >= options["batch"]:
                        ArticleKeyword.objects.bulk_create(
                            buffer, ignore_conflicts=True
                        )
                        buffer = []
            if buffer:
                ArticleKeyword.objects.bulk_create(buffer, ignore_conflicts=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово. Статей: {n_articles}, ключевых слов: {n_words} (сырьё)."
            )
        )
        if missing_articles:
            self.stdout.write(f"Пропущено статей (нет в БД): {missing_articles}")
