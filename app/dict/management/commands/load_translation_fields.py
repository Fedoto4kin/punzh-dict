import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from dict.models import Article, ArticleSemanticField, SemanticField


class Command(BaseCommand):
    help = (
        "Проставить from_translation на уже существующих связях "
        "ArticleSemanticField из json "
        '(формат: {"from_translation": {article_id: [field_name, ...]}}). '
        "Пустой список — все флаги статьи False. Связи не удаляются и не "
        "создаются. Статьи вне json не трогаются."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", required=True, help="Путь к json пометки «по переводу»."
        )

    def handle(self, *args, **options):
        path = options["file"]
        if not os.path.exists(path):
            self.stderr.write(f"Файл не найден: {path}")
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        mapping = data.get("from_translation")
        if mapping is None:
            self.stderr.write("В json нет ключа 'from_translation'.")
            return
        if not mapping:
            self.stderr.write("В json 'from_translation' пусто.")
            return
        self.stdout.write(f"Статей в json: {len(mapping)}")

        field_id_by_name = dict(SemanticField.objects.values_list("name", "id"))

        article_ids = []
        for aid in mapping.keys():
            try:
                article_ids.append(int(aid))
            except (TypeError, ValueError):
                continue

        existing = set(
            Article.objects.filter(id__in=article_ids).values_list("id", flat=True)
        )

        n_set = 0
        missing_articles = 0
        missing_fields = {}
        missing_links = 0

        with transaction.atomic():
            ArticleSemanticField.objects.filter(article_id__in=existing).update(
                from_translation=False
            )
            for aid_str, names in mapping.items():
                try:
                    aid = int(aid_str)
                except (TypeError, ValueError):
                    continue
                if aid not in existing:
                    missing_articles += 1
                    continue
                if isinstance(names, str):
                    names = [names]
                for name in names or []:
                    fid = field_id_by_name.get(name)
                    if fid is None:
                        missing_fields[name] = missing_fields.get(name, 0) + 1
                        continue
                    updated = ArticleSemanticField.objects.filter(
                        article_id=aid, field_id=fid
                    ).update(from_translation=True)
                    if updated:
                        n_set += 1
                    else:
                        missing_links += 1

        self.stdout.write(
            self.style.SUCCESS(f"Готово. Пометок «по переводу»: {n_set}.")
        )
        if missing_articles:
            self.stdout.write(f"Пропущено статей (нет в БД): {missing_articles}")
        if missing_links:
            self.stdout.write(
                f"Нет связи статья↔поле (флаг не ставили): {missing_links}"
            )
        if missing_fields:
            self.stdout.write("Поля из json, которых НЕТ в справочнике (пропущены):")
            for name, cnt in sorted(missing_fields.items(), key=lambda x: -x[1]):
                self.stdout.write(f"  {cnt:5d}  {name!r}")
