import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from dict.models import Article, SemanticField, ArticleSemanticField


class Command(BaseCommand):
    help = (
        "Залить привязки статья→смысловое поле из json классификатора "
        '(формат: {"assignments": {article_id: [field_name, ...]}}). '
        "Жёстко: json — источник истины. Для статей, упомянутых в json, "
        "существующие привязки удаляются и создаются заново. Статьи вне json "
        "не трогаются. Поля ищутся по имени в SemanticField."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Путь к json классификации.")
        parser.add_argument(
            "--batch",
            type=int,
            default=1000,
            help="Размер пачки bulk_create (по умолчанию 1000).",
        )

    def handle(self, *args, **options):
        path = options["file"]
        if not os.path.exists(path):
            self.stderr.write(f"Файл не найден: {path}")
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assignments = data.get("assignments") or {}
        if not assignments:
            self.stderr.write("В json нет 'assignments' или пусто.")
            return
        self.stdout.write(f"Статей в json: {len(assignments)}")

        # справочник имя->id одним запросом
        field_id_by_name = dict(SemanticField.objects.values_list("name", "id"))

        # id статей из json (ключи — строки)
        article_ids = []
        for aid in assignments.keys():
            try:
                article_ids.append(int(aid))
            except (TypeError, ValueError):
                continue

        # какие article_id реально существуют (чтобы FK не падал)
        existing = set(
            Article.objects.filter(id__in=article_ids).values_list("id", flat=True)
        )

        buffer = []
        n_links = 0
        n_articles = 0
        missing_fields = {}  # имя поля -> сколько раз встретилось, но нет в справочнике
        missing_articles = 0

        with transaction.atomic():
            # жёстко: снять привязки только для статей из json
            ArticleSemanticField.objects.filter(article_id__in=existing).delete()

            for aid_str, field_names in assignments.items():
                try:
                    aid = int(aid_str)
                except (TypeError, ValueError):
                    continue
                if aid not in existing:
                    missing_articles += 1
                    continue
                n_articles += 1
                for name in field_names or []:
                    fid = field_id_by_name.get(name)
                    if fid is None:
                        missing_fields[name] = missing_fields.get(name, 0) + 1
                        continue
                    buffer.append(ArticleSemanticField(article_id=aid, field_id=fid))
                    n_links += 1
                    if len(buffer) >= options["batch"]:
                        ArticleSemanticField.objects.bulk_create(
                            buffer, ignore_conflicts=True
                        )
                        buffer = []
            if buffer:
                ArticleSemanticField.objects.bulk_create(buffer, ignore_conflicts=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово. Статей размечено: {n_articles}, привязок: {n_links}."
            )
        )
        if missing_articles:
            self.stdout.write(f"Пропущено статей (нет в БД): {missing_articles}")
        if missing_fields:
            self.stdout.write("Поля из json, которых НЕТ в справочнике (пропущены):")
            for name, cnt in sorted(missing_fields.items(), key=lambda x: -x[1]):
                self.stdout.write(f"  {cnt:5d}  {name!r}")
