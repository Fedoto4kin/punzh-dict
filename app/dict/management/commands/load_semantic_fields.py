import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from dict.models import SemanticField, ArticleSemanticField


DEFAULT_REL = "dict/fixtures/custom/ontology_frozen.json"


class Command(BaseCommand):
    help = (
        "Наполнить справочник SemanticField из онтологии (наш формат: "
        '{"ontology": [{"field","definition"}]}). '
        "По умолчанию — мягко (update_or_create: обновить определения, добавить "
        "новые, ничего не удалять). С --force — снести ВЕСЬ справочник и "
        "создать заново; ВНИМАНИЕ: каскадом удалятся все привязки "
        "ArticleSemanticField (классификация статей)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=None,
            help=f"Путь к json (по умолчанию {DEFAULT_REL} от BASE_DIR).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Снести весь справочник и пересоздать (сотрёт привязки каскадом).",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Не спрашивать подтверждение при --force.",
        )

    def _resolve_path(self, file_arg):
        if file_arg:
            return file_arg
        base = getattr(settings, "BASE_DIR", os.getcwd())
        return os.path.join(str(base), DEFAULT_REL)

    def handle(self, *args, **options):
        path = self._resolve_path(options["file"])
        if not os.path.exists(path):
            self.stderr.write(f"Файл не найден: {path}")
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ontology = data.get("ontology")
        if not ontology:
            self.stderr.write("В json нет ключа 'ontology' или он пуст.")
            return
        self.stdout.write(f"Полей в онтологии: {len(ontology)}")

        if options["force"]:
            self._force_reload(ontology, options["yes"])
        else:
            self._soft_upsert(ontology)

    def _soft_upsert(self, ontology):
        created, updated = 0, 0
        with transaction.atomic():
            for i, item in enumerate(ontology):
                name = item["field"]
                defaults = {
                    "definition": item.get("definition", ""),
                    "sorting": i,
                }
                obj, was_created = SemanticField.objects.update_or_create(
                    name=name, defaults=defaults
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Мягко: создано {created}, обновлено {updated}. "
                f"Ничего не удалено, привязки целы."
            )
        )

    def _force_reload(self, ontology, assume_yes):
        n_fields = SemanticField.objects.count()
        n_links = ArticleSemanticField.objects.count()
        self.stdout.write(
            self.style.WARNING(
                f"--force снесёт ВЕСЬ справочник ({n_fields} полей) и КАСКАДОМ "
                f"все привязки ArticleSemanticField ({n_links} шт.)."
            )
        )
        if not assume_yes:
            answer = input("Продолжить? Введите 'yes' для подтверждения: ")
            if answer.strip().lower() != "yes":
                self.stdout.write("Отменено.")
                return

        with transaction.atomic():
            SemanticField.objects.all().delete()  # ArticleSemanticField уйдёт каскадом
            objs = []
            for i, item in enumerate(ontology):
                objs.append(
                    SemanticField(
                        name=item["field"],
                        definition=item.get("definition", ""),
                        sorting=i,
                    )
                )
            SemanticField.objects.bulk_create(objs)
        self.stdout.write(
            self.style.SUCCESS(
                f"Force: справочник пересоздан ({len(objs)} полей). "
                f"Привязки удалены ({n_links})."
            )
        )
