"""Кириллица в карельских заголовках и индексе. Только отчёт, ничего не пишет."""

import csv
from collections import Counter

from django.core.management.base import BaseCommand

from dict.cyrillic_audit import cyrillic_chars, describe_char, suggest_latin
from dict.models import Article, ArticleIndexWord, ArticleIndexWordNormalization

ARTICLE_FIELDS = (
    ("word", "Article.word"),
    ("word_normalized", "Article.word_normalized"),
    ("first_letter", "Article.first_letter"),
)


def _hit(article_id, field, value, existing_words):
    bad = cyrillic_chars(value)
    suggested = suggest_latin(value)
    collision = existing_words.get(suggested)
    return {
        "article_id": article_id,
        "field": field,
        "value": value,
        "chars": "; ".join(describe_char(ch) for ch in bad),
        "suggested": suggested,
        "collision_id": collision if collision and collision != article_id else "",
        "cyr_letters": bad,
    }


def scan_cyrillic_lemmas():
    """
    Headword fields first; index rows only when the article headword
    (word and word_normalized) has no Cyrillic — leftover/corrupt index.
    """
    existing_words = {w: pk for pk, w in Article.objects.values_list("id", "word") if w}

    headword_rows = []
    dirty_headword_ids = set()
    for pk, word, word_normalized, first_letter in Article.objects.values_list(
        "id", "word", "word_normalized", "first_letter"
    ).iterator(chunk_size=500):
        values = {
            "word": word,
            "word_normalized": word_normalized,
            "first_letter": first_letter,
        }
        for key, label in ARTICLE_FIELDS:
            if cyrillic_chars(values[key]):
                headword_rows.append(_hit(pk, label, values[key], existing_words))
                if key in ("word", "word_normalized"):
                    dirty_headword_ids.add(pk)

    index_rows = []
    for model, label in (
        (ArticleIndexWord, "ArticleIndexWord.word"),
        (ArticleIndexWordNormalization, "ArticleIndexWordNormalization.word"),
    ):
        qs = model.objects.values_list("id", "article_id", "word")
        if dirty_headword_ids:
            qs = qs.exclude(article_id__in=dirty_headword_ids)
        for row_id, article_id, word in qs.iterator(chunk_size=1000):
            if not cyrillic_chars(word):
                continue
            hit = _hit(article_id, f"{label}#{row_id}", word, existing_words)
            index_rows.append(hit)

    return headword_rows, index_rows


class Command(BaseCommand):
    help = (
        "Найти кириллицу в карельских заголовках и словесном индексе. "
        "Только отчёт, БД не меняет."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            action="store_true",
            help="Таблица в stdout (удобно перенаправить в файл).",
        )

    def handle(self, *args, **opts):
        headword_rows, index_rows = scan_cyrillic_lemmas()
        rows = headword_rows + index_rows

        if opts["csv"]:
            writer = csv.DictWriter(
                self.stdout,
                fieldnames=[
                    "article_id",
                    "field",
                    "value",
                    "chars",
                    "suggested",
                    "collision_id",
                ],
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row[k] for k in writer.fieldnames})
            return

        letters = Counter()
        for row in rows:
            letters.update(row["cyr_letters"])

        hw_arts = {r["article_id"] for r in headword_rows}
        idx_arts = {r["article_id"] for r in index_rows}
        self.stdout.write(
            f"Заголовки (word / word_normalized / first_letter): "
            f"{len(headword_rows)} строк, {len(hw_arts)} статей"
        )
        self.stdout.write(
            f"Индекс при чистом заголовке: "
            f"{len(index_rows)} строк, {len(idx_arts)} статей"
        )
        if letters:
            self.stdout.write("Буквы:")
            for ch, n in letters.most_common():
                self.stdout.write(f"  {n:4d}  {describe_char(ch)}")
        self.stdout.write("")

        if not rows:
            self.stdout.write("Кириллицы в заголовках и индексе нет.")
            return

        for row in rows:
            extra = (
                f"  !! совпадёт со статьёй {row['collision_id']}"
                if row["collision_id"]
                else ""
            )
            self.stdout.write(
                f"#{row['article_id']}  {row['field']}\n"
                f"    сейчас:     {row['value']!r}\n"
                f"    символы:    {row['chars']}\n"
                f"    предложено: {row['suggested']!r}{extra}"
            )
