import os

from django.conf import settings
from django.contrib.postgres.search import SearchVector
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from dict.models import Article, ArticleIndexTranslate, ArticleIndexWord


DEFAULT_REL = "dict/fixtures/dict_seed.json"


class Command(BaseCommand):
    help = (
        "Очистить все таблицы dict, загрузить fixture и пересобрать индексы "
        "слов и search_vector переводов. На продакшене (DEBUG=False) — только "
        "с осознанным подтверждением."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=None,
            help=f"Путь к json (по умолчанию {DEFAULT_REL} от BASE_DIR).",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Не спрашивать подтверждение на dev (DEBUG=True).",
        )
        parser.add_argument(
            "--allow-production",
            action="store_true",
            help="Разрешить неинтерактивный запуск при DEBUG=False (только с --yes).",
        )
        parser.add_argument(
            "--skip-reindex",
            action="store_true",
            help="Только очистка и loaddata, без пересборки индексов.",
        )

    def _resolve_path(self, file_arg):
        if file_arg:
            return file_arg
        base = getattr(settings, "BASE_DIR", os.getcwd())
        return os.path.join(str(base), DEFAULT_REL)

    def _truncate_dict(self):
        tables = [
            t for t in connection.introspection.table_names() if t.startswith("dict_")
        ]
        if not tables:
            return 0
        quoted = ", ".join(connection.ops.quote_name(t) for t in tables)
        with connection.cursor() as cursor:
            cursor.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")
        return len(tables)

    def _confirm_destructive(self, options, fixture_path):
        if not settings.DEBUG:
            self.stderr.write(
                self.style.WARNING(
                    "\n"
                    "ВНИМАНИЕ: DEBUG=False — похоже на ПРОДАКШЕН.\n"
                    "Будут удалены ВСЕ данные приложения dict и загружен fixture.\n"
                    "Действие необратимо без бэкапа БД.\n"
                )
            )

        self.stdout.write(f"Fixture: {fixture_path}")

        if settings.DEBUG:
            if options["yes"]:
                return True
            answer = input("Продолжить? [y/N] ").strip().lower()
            return answer in ("y", "yes", "д", "да")

        if options["yes"] and options["allow_production"]:
            self.stderr.write(
                self.style.WARNING(
                    "Продолжаем на продакшене (--yes --allow-production)."
                )
            )
            return True

        answer = input(
            "Продакшен: введите 'yes' для подтверждения (или Ctrl+C): "
        ).strip()
        if answer.lower() != "yes":
            self.stdout.write("Отменено.")
            return False
        return True

    def _reindex_words(self):
        n = 0
        for art in Article.objects.all().iterator(chunk_size=500):
            art.save()
            n += 1
            if n % 1000 == 0:
                self.stdout.write(f"  reindex words: {n}")
        self.stdout.write(f"reindex words done: {n}")

    def _reindex_translations(self):
        n = ArticleIndexTranslate.objects.update(
            search_vector=SearchVector("rus_word", config="simple")
        )
        self.stdout.write(f"search_vector: {n}")

    def handle(self, *args, **options):
        path = self._resolve_path(options["file"])
        if not os.path.exists(path):
            self.stderr.write(self.style.ERROR(f"Файл не найден: {path}"))
            return

        if not self._confirm_destructive(options, path):
            return

        # TRUNCATE нельзя в той же транзакции, где уже меняли строки этих таблиц.
        transaction.commit()
        n_tables = self._truncate_dict()
        self.stdout.write(f"Очищено таблиц: {n_tables}")

        with transaction.atomic():
            call_command("loaddata", path, verbosity=1)

        if not options["skip_reindex"]:
            self._reindex_words()
            self._reindex_translations()

        self.stdout.write(self.style.SUCCESS("Готово."))
