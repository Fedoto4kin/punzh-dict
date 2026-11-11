"""Corpus DF of rus_word tokens → stopword candidates for query token-OR (variant A)."""

import csv

from django.core.management.base import BaseCommand

from dict.query_stopword_audit import (
    csv_rows,
    format_python_set,
    scan_query_stopword_candidates,
)


class Command(BaseCommand):
    help = (
        "Частоты токенов ArticleIndexTranslate.rus_word: DF, скобочные лиды, "
        "дыры 1a/1b и кандидаты 1c для QUERY_STOP (вариант A). "
        "Только отчёт, БД не меняет."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-df",
            type=int,
            default=30,
            help="Порог DF (число статей) для missing_1a / candidate_1c / review "
            "(по умолчанию 30).",
        )
        parser.add_argument(
            "--max-len-1c",
            type=int,
            default=5,
            help="Макс. длина токена для корзин candidate_1c и review (по умолчанию 5).",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=80,
            help="Сколько строк токенов показать в таблице (по умолчанию 80; "
            "0 = все после фильтра --bucket).",
        )
        parser.add_argument(
            "--bucket",
            action="append",
            dest="buckets",
            choices=(
                "stop_1a",
                "stop_1b",
                "missing_1a",
                "missing_1b",
                "candidate_1c",
                "review",
                "content",
            ),
            help="Оставить только эти корзины в таблице (можно повторять).",
        )
        parser.add_argument(
            "--csv",
            action="store_true",
            help="Таблица в stdout (удобно перенаправить в файл).",
        )
        parser.add_argument(
            "--suggest",
            action="store_true",
            help="В конце напечатать черновик Python-множества _STOP_1C.",
        )

    def handle(self, *args, **opts):
        top = opts["top"]
        audit = scan_query_stopword_candidates(
            min_df=opts["min_df"],
            max_len_1c=opts["max_len_1c"],
            top=None if top == 0 else top,
            buckets=opts["buckets"],
        )

        if opts["csv"]:
            writer = csv.DictWriter(
                self.stdout,
                fieldnames=[
                    "token",
                    "len",
                    "df",
                    "rows",
                    "paren_lead_df",
                    "bucket",
                    "in_stopwords",
                    "in_seed_1c",
                ],
                lineterminator="\n",
            )
            writer.writeheader()
            for row in csv_rows(audit.stats):
                writer.writerow(row)
            return

        self.stdout.write(
            f"Статей с переводами: {audit.article_count}, "
            f"строк rus_word: {audit.row_count}, "
            f"различных токенов: {audit.distinct_tokens}, "
            f"min_df={opts['min_df']}, max_len_1c={opts['max_len_1c']}."
        )
        self.stdout.write("")
        self.stdout.write(
            f"{'token':<16} {'len':>3} {'df':>6} {'rows':>6} " f"{'paren':>5}  bucket"
        )
        self.stdout.write("-" * 56)
        for s in audit.stats:
            self.stdout.write(
                f"{s.token:<16} {s.length:>3} {s.df:>6} {s.rows:>6} "
                f"{s.paren_lead_df:>5}  {s.bucket}"
            )

        self.stdout.write("")
        self.stdout.write(
            f"missing_1a ({len(audit.missing_1a)}): "
            + (", ".join(audit.missing_1a) if audit.missing_1a else "—")
        )
        self.stdout.write(
            f"missing_1b-like ({len(audit.missing_1b_like)}): "
            + (", ".join(audit.missing_1b_like) if audit.missing_1b_like else "—")
        )
        self.stdout.write(
            f"suggested_1c ({len(audit.suggested_1c)}): "
            + (", ".join(audit.suggested_1c) if audit.suggested_1c else "—")
        )

        if opts["suggest"]:
            self.stdout.write("")
            self.stdout.write(format_python_set("_STOP_1C", audit.suggested_1c))
