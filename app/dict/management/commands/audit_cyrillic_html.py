"""Кириллица в карельских фрагментах article_html. Только отчёт."""

import csv
from collections import Counter

from django.core.management.base import BaseCommand

from dict.cyrillic_audit import describe_char, scan_cyrillic_in_html


class Command(BaseCommand):
    help = (
        "Найти кириллицу в карельских кусках article_html: "
        "смешанный алфавит в токене и любая кириллица сразу после ~. "
        "Показывает слово (lemma) и HTML статьи. БД не меняет. "
        "Правка: fix_cyrillic_html."
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
            choices=("all", "homoglyph", "non_homoglyph"),
            default="all",
            help="homoglyph — только омоглифы; non_homoglyph — остальное.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Показать не больше N хитов.",
        )

    def handle(self, *args, **opts):
        rows, letters = scan_cyrillic_in_html()
        kind = opts["kind"]
        if kind != "all":
            rows = [r for r in rows if r["kind"] == kind]
        queue = opts["queue"]
        if queue == "homoglyph":
            rows = [r for r in rows if r["homoglyph_only"]]
        elif queue == "non_homoglyph":
            rows = [r for r in rows if not r["homoglyph_only"]]
        if kind != "all" or queue != "all":
            letters = Counter()
            for row in rows:
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
                        "homoglyph_only": row["homoglyph_only"],
                        "value": row["value"],
                        "offset": row["offset"],
                        "chars": row["chars"],
                        "suggested": row["suggested"],
                    }
                )
            return

        by_kind = Counter(r["kind"] for r in rows)
        arts = {r["article_id"] for r in rows}
        n_homo = sum(1 for r in rows if r["homoglyph_only"])
        self.stdout.write(
            f"Находок: {len(rows)}, статей: {len(arts)} "
            f"(after_tilde={by_kind['after_tilde']}, mixed={by_kind['mixed']}, "
            f"homoglyph_only={n_homo})"
        )
        if letters:
            self.stdout.write("Буквы:")
            for ch, n in letters.most_common():
                self.stdout.write(f"  {n:4d}  {describe_char(ch)}")
        self.stdout.write("")

        if not rows:
            self.stdout.write("Кириллицы в карельских фрагментах HTML нет.")
            return

        for row in rows:
            flag = "homoglyph" if row["homoglyph_only"] else "NON-homoglyph"
            self.stdout.write("=" * 72)
            self.stdout.write(
                f"#{row['article_id']}  {row.get('word')!s}  "
                f"{row['kind']}  ({flag})"
            )
            self.stdout.write("-" * 72)
            self.stdout.write(row.get("article_html") or "(html пуст)")
            self.stdout.write("-" * 72)
            self.stdout.write(f"    сейчас:     {row['value']!r}")
            self.stdout.write(f"    символы:    {row['chars']}")
            self.stdout.write(f"    предложено: {row['suggested']!r}")
            self.stdout.write("")
