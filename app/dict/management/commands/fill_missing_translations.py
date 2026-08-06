import re

from django.core.management.base import BaseCommand
from django.db import transaction

from dict.helpers import normalization
from dict.models import Article, ArticleIndexTranslate, ArticleLink


# Split a single input line into several translations at ";" (and, optionally,
# a plain "," — off by default because commas legitimately appear inside a
# gloss). Whitespace is collapsed the same way we cleaned the import artifacts.
SPLIT_RE = re.compile(r"\s*;\s*")


class Command(BaseCommand):
    help = (
        "Интерактивный добор переводов для статей БЕЗ единого перевода. "
        "По каждой статье показывает html и заголовок, принимает один или "
        "несколько переводов (разделитель ';'), сохраняет в "
        "ArticleIndexTranslate и переходит к следующей. "
        "Команды в поле ввода: пустая строка — пропустить статью; 'u' — "
        "отменить перевод(ы), только что сохранённые для этой статьи; "
        "'q' — сохранить и выйти. search_vector НЕ трогаем (полнотекст "
        "пересобирается отдельно)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Обработать не больше N статей за сессию.",
        )
        parser.add_argument(
            "--order",
            choices=["word", "id"],
            default="word",
            help="Порядок обхода: по слову (по умолчанию) или по id.",
        )
        parser.add_argument(
            "--split-comma",
            action="store_true",
            help="Разбивать ввод ещё и по запятой (по умолчанию только по ';').",
        )

    # --- helpers -------------------------------------------------------------

    def _clean(self, s):
        return re.sub(r"\s+", " ", s).strip()

    def _parse(self, line, split_comma):
        parts = SPLIT_RE.split(line)
        if split_comma:
            expanded = []
            for p in parts:
                expanded.extend(p.split(","))
            parts = expanded
        out = []
        seen = set()
        for p in parts:
            c = self._clean(p)
            key = c.lower()
            if c and key not in seen:
                seen.add(key)
                out.append(c)
        return out

    def _save(self, article, translations):
        # Returns the list of ArticleIndexTranslate ids actually created, so the
        # 'u' (undo) command can remove exactly this article's additions.
        created = []
        with transaction.atomic():
            for rus in translations:
                obj, was_created = ArticleIndexTranslate.objects.get_or_create(
                    article=article, rus_word=rus
                )
                if was_created:
                    created.append(obj.id)
        return created

    # --- main ----------------------------------------------------------------

    def handle(self, *args, **opts):
        split_comma = opts["split_comma"]

        # 1) articles with NO translation at all, EXCLUDING «см.» references
        # (their meaning lives in the donor — no translation to enter by hand).
        # A reference = has linked_article set, OR appears as from_article in
        # ArticleLink (the "X см. Y" side). Being a donor (to_article) is NOT a
        # reason to hide it. Textual "см." in html without a real link is left
        # in the queue and shown as an ordinary article (per operator's choice).
        with_tr = ArticleIndexTranslate.objects.values_list(
            "article_id", flat=True
        ).distinct()
        ref_ids = set(
            Article.objects.filter(linked_article__isnull=False).values_list(
                "id", flat=True
            )
        )
        ref_ids |= set(
            ArticleLink.objects.values_list("from_article_id", flat=True)
        )
        self.stdout.write(f"Исключено статей-отсылок (см.): {len(ref_ids)}")

        qs = Article.objects.exclude(id__in=with_tr).exclude(id__in=ref_ids)
        qs = qs.order_by("word" if opts["order"] == "word" else "id")
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        total = qs.count()
        if not total:
            self.stdout.write(self.style.SUCCESS("Статей без перевода нет. Нечего делать."))
            return

        self.stdout.write(
            self.style.WARNING(
                f"Статей без перевода: {total}. "
                f"Ввод: перевод(ы) через ';'. Пусто — пропустить, "
                f"'u' — отменить сохранённое по этой статье, 'q' — выйти."
            )
        )

        done = 0
        added = 0
        skipped = 0
        # Materialize ids up front: we mutate translations as we go, and we do
        # not want the queryset to shift under us mid-session.
        ids = list(qs.values_list("id", flat=True))

        for idx, aid in enumerate(ids, start=1):
            try:
                article = Article.objects.get(id=aid)
            except Article.DoesNotExist:
                continue

            # Re-check: it might have gained a translation earlier this session
            # (e.g. same article surfaced twice — shouldn't, but be safe).
            if ArticleIndexTranslate.objects.filter(article_id=aid).exists():
                continue

            last_created = []
            while True:
                self.stdout.write("\n" + "=" * 72)
                self.stdout.write(f"[{idx}/{total}]  id={article.id}")
                self.stdout.write(f"Заголовок: {normalization(article.word)}")
                self.stdout.write("-" * 72)
                self.stdout.write(article.article_html or "(html пуст)")
                self.stdout.write("-" * 72)

                try:
                    line = input("Перевод(ы) / пусто=пропуск / u=отмена / q=выход: ")
                except (EOFError, KeyboardInterrupt):
                    self.stdout.write("\nВыход.")
                    self._summary(done, added, skipped)
                    return

                cmd = line.strip().lower()

                if cmd == "q":
                    self.stdout.write("Выход по 'q'.")
                    self._summary(done, added, skipped)
                    return

                if cmd == "u":
                    if last_created:
                        n, _ = ArticleIndexTranslate.objects.filter(
                            id__in=last_created
                        ).delete()
                        added -= len(last_created)
                        self.stdout.write(self.style.WARNING(f"Отменено записей: {len(last_created)}."))
                        last_created = []
                        # stay on the same article for another attempt
                        continue
                    else:
                        self.stdout.write("Отменять нечего для этой статьи.")
                        continue

                if line.strip() == "":
                    skipped += 1
                    self.stdout.write("Пропущено.")
                    break

                translations = self._parse(line, split_comma)
                if not translations:
                    self.stdout.write("Пусто после очистки — введите ещё раз или пусто для пропуска.")
                    continue

                created = self._save(article, translations)
                last_created = created
                added += len(created)
                done += 1
                shown = ", ".join(translations)
                dup = len(translations) - len(created)
                msg = f"Сохранено: {shown}"
                if dup:
                    msg += f" (пропущено дублей: {dup})"
                self.stdout.write(self.style.SUCCESS(msg))
                # move on to the next article
                break

        self.stdout.write("\nСписок закончился.")
        self._summary(done, added, skipped)

    def _summary(self, done, added, skipped):
        self.stdout.write(
            self.style.SUCCESS(
                f"Итог: статей с добавленным переводом — {done}, "
                f"переводов создано — {added}, пропущено — {skipped}."
            )
        )
