"""Смешанный алфавит в article_html. Только отчёт."""

import csv
from collections import Counter

from django.core.management.base import BaseCommand

from dict.cyrillic_audit import describe_char, latin_leak_chars, scan_cyrillic_in_html


class Command(BaseCommand):
    help = (
        "Найти смешанный алфавит в article_html: "
        "кириллица в карельском (после ~ / mid-word) и латиница в русском. "
        "Показывает слово и HTML. БД не меняет. Правка: fix_cyrillic_html."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            action="store_true",
            help="Таблица в stdout (удобно перенаправить в файл).",
        )
        parser.add_argument(
            "--kind",
            choices=("all", "after_tilde", "mixed"),
            default="all",
            help="Фильтр вида находки (по умолчанию все).",
        )
        parser.add_argument(
            "--queue",
            choices=("all", "homoglyph", "krl", "rus", "non_homoglyph"),
            default="all",
            help=(
                "homoglyph|krl — карельский (кир.→лат.); "
                "rus|non_homoglyph — русский (лат.→кир.)."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Показать не больше N хитов.",
        )

    def _filter_rows(self, rows, kind, queue):
        if kind != "all":
            rows = [r for r in rows if r["kind"] == kind]
        if queue in ("homoglyph", "krl"):
            rows = [r for r in rows if r["direction"] == "krl"]
        elif queue in ("rus", "non_homoglyph"):
            rows = [r for r in rows if r["direction"] == "rus"]
        return rows

    def handle(self, *args, **opts):
        rows, letters = scan_cyrillic_in_html()
        rows = self._filter_rows(rows, opts["kind"], opts["queue"])
        if opts["kind"] != "all" or opts["queue"] != "all":
            letters = Counter()
            for row in rows:
                if row["direction"] == "rus":
                    letters.update(latin_leak_chars(row["value"]))
                else:
                    letters.update(row["cyr_letters"])
        if opts["limit"]:
            rows = rows[: opts["limit"]]

        if opts["csv"]:
            writer = csv.DictWriter(
                self.stdout,
                fieldnames=[
                    "article_id",
                    "word",
                    "kind",
                    "direction",
                    "homoglyph_only",
                    "value",
                    "offset",
                    "chars",
                    "suggested",
                ],
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "article_id": row["article_id"],
                        "word": row.get("word", ""),
                        "kind": row["kind"],
                        "direction": row["direction"],
                        "homoglyph_only": row["homoglyph_only"],
                        "value": row["value"],
                        "offset": row["offset"],
                        "chars": row["chars"],
                        "suggested": row["suggested"],
                    }
                )
            return

        by_kind = Counter(r["kind"] for r in rows)
        by_dir = Counter(r["direction"] for r in rows)
        arts = {r["article_id"] for r in rows}
        self.stdout.write(
            f"Находок: {len(rows)}, статей: {len(arts)} "
            f"(after_tilde={by_kind['after_tilde']}, mixed={by_kind['mixed']}, "
            f"krl={by_dir['krl']}, rus={by_dir['rus']})"
        )
        if letters:
            self.stdout.write("Буквы (в направлении правки):")
            for ch, n in letters.most_common():
                self.stdout.write(f"  {n:4d}  {describe_char(ch)}")
        self.stdout.write("")

        if not rows:
            self.stdout.write("Смешанного алфавита в HTML нет.")
            return

        for row in rows:
            label = "krl: кир→лат" if row["direction"] == "krl" else "rus: лат→кир"
            self.stdout.write("=" * 72)
            self.stdout.write(
                f"#{row['article_id']}  {row.get('word')!s}  "
                f"{row['kind']}  ({label})"
            )
            self.stdout.write("-" * 72)
            self.stdout.write(row.get("article_html") or "(html пуст)")
            self.stdout.write("-" * 72)
            self.stdout.write(f"    сейчас:     {row['value']!r}")
            self.stdout.write(f"    символы:    {row['chars']}")
            self.stdout.write(f"    предложено: {row['suggested']!r}")
            self.stdout.write("")
