"""
Classify one article by id against the ontology in the DB.

Runtime counterpart of agents/build_ontology.py --ontology: same frozen
prompt, but via the Timeweb gateway (TIMEWEB_AI_MODEL_CLASSIFY) and writing
straight to ArticleSemanticField / ArticleKeyword.

Callable later from a background worker — the core is dict.ai.classify.

    docker exec --user 1000:1000 -w /app punzh_django \\
      python manage.py classify_article --id 12345
"""

from django.core.management.base import BaseCommand, CommandError

from dict.ai.classify import classify_article


class Command(BaseCommand):
    help = (
        "Доклассифицировать одну статью по онтологии из БД "
        "(DeepSeek через шлюз Timeweb)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--id", type=int, required=True, help="id статьи.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только ответ модели, без записи в БД.",
        )

    def handle(self, *args, **options):
        article_id = options["id"]
        persist = not options["dry_run"]
        result = classify_article(article_id, persist=persist)
        if not result["ok"]:
            raise CommandError(
                f"классификация id={article_id} не удалась: {result['error']}"
            )
        fields = ", ".join(result["fields"]) or "—"
        tr_fields = ", ".join(result["translation_fields"]) or "—"
        keywords = ", ".join(result["keywords"]) or "—"
        mode = "dry-run" if result["dry_run"] else "записано"
        extra = ""
        if result.get("error"):
            extra = f"  предупреждение={result['error']}"
        self.stdout.write(
            self.style.SUCCESS(
                f"id={article_id}  поля: {fields}  по переводу: {tr_fields}  "
                f"keywords: {keywords}  no_field={result['no_field']}  "
                f"({mode}){extra}"
            )
        )
