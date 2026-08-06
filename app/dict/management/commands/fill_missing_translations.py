import re
import sys

from django.core.management.base import BaseCommand
from django.db import transaction

from dict.helpers import normalization
from dict.models import Article, ArticleIndexTranslate, ArticleLink


# Split a single input line into several translations at ";" (and, optionally,
# a plain "," — off by default because commas legitimately appear inside a
# gloss). Whitespace is collapsed the same way we cleaned the import artifacts.
SPLIT_RE = re.compile(r"\s*;\s*")

# html-content markers of articles that carry no own meaning and must be kept
# OUT of the manual-translation queue (their links are to be repaired later):
#   1) a cross-reference «см.» rendered as an italic помета  <i>см.</i>
#      (matched as the italic marker, NOT bare "см", to avoid catching
#       illustrations with "смех", "смотреть", "5 см." etc.);
#   2) a derived grammatical form "от <карельское слово>" — "от" as a standalone
#      token followed by a LATIN word (the base lemma). Russian "от" in an
#      illustration is followed by Cyrillic, so it does not match.
SEE_RE = re.compile(r"<i>\s*см\.?\s*</i>", re.IGNORECASE)
DERIV_RE = re.compile(r"(?:^|[\s>])от\s+[A-Za-zÀ-ÿ]", re.IGNORECASE)


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

    def _ask(self, prompt):
        # Read a line as raw bytes straight from stdin and decode UTF-8 ourselves.
        # Going through input()/GNU-readline breaks in containers with a non-UTF-8
        # locale: readline mangles multibyte input, giving either surrogates
        # (which then blow up on DB write) or a UnicodeDecodeError on the read
        # itself. Reading sys.stdin.buffer sidesteps readline and the locale.
        sys.stdout.write(prompt)
        sys.stdout.flush()
        raw = sys.stdin.buffer.readline()
        if raw == b"":
            raise EOFError
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        # Strip stray control bytes (e.g. a layout/compose-switch keystroke that
        # the terminal injects into stdin) and the U+FFFD replacement char left
        # by any undecodable byte — they are never part of a translation and on
        # prod they break the DB write.
        line = "".join(
            ch for ch in line if ch == "\t" or (ord(ch) >= 32 and ch != "\ufffd")
        )
        return line

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
        ref_ids |= set(ArticleLink.objects.values_list("from_article_id", flat=True))
        self.stdout.write(f"Исключено статей-отсылок (см.): {len(ref_ids)}")

        qs = Article.objects.exclude(id__in=with_tr).exclude(id__in=ref_ids)
        qs = qs.order_by("word" if opts["order"] == "word" else "id")

        # html-level exclusion: textual «см.» references without a real link, and
        # derived grammatical forms "от <lemma>". Both are repaired separately —
        # not by entering translations here.
        ids = []
        n_see = 0
        n_deriv = 0
        for aid, html in qs.values_list("id", "article_html"):
            html = html or ""
            if SEE_RE.search(html):
                n_see += 1
                continue
            if DERIV_RE.search(html):
                n_deriv += 1
                continue
            ids.append(aid)
        self.stdout.write(
            f"Исключено по html: «см.» без ссылки — {n_see}, "
            f"деривации «от <слово>» — {n_deriv}."
        )

        if opts["limit"]:
            ids = ids[: opts["limit"]]

        total = len(ids)
        if not total:
            self.stdout.write(
                self.style.SUCCESS("Статей без перевода нет. Нечего делать.")
            )
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
        # ids is already materialized above (after html-level filtering).

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
                    line = self._ask(
                        "Перевод(ы) / пусто=пропуск / u=отмена / q=выход: "
                    )
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
                        self.stdout.write(
                            self.style.WARNING(
                                f"Отменено записей: {len(last_created)}."
                            )
                        )
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
                    self.stdout.write(
                        "Пусто после очистки — введите ещё раз или пусто для пропуска."
                    )
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
