"""Полуавтоматическая правка кириллицы в карельских фрагментах article_html."""

import sys

from django.core.management.base import BaseCommand
from django.db import transaction

from dict.cyrillic_audit import (
    apply_token_fix,
    find_html_cyrillic_leaks,
    scan_cyrillic_in_html,
)
from dict.models import Article


class Command(BaseCommand):
    help = (
        "Правка смешанного алфавита в article_html (как fix_see_refs). "
        "Очереди: homoglyph/krl — кириллица→латиница в карельском; "
        "rus/non_homoglyph — латиница→кириллица в русском. "
        "y — заменить, пусто — пропуск, u — отмена, q — выход. "
        "Нужен TTY: docker exec -it … python manage.py fix_cyrillic_html"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Не больше N хитов за сессию.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать очередь (слово + статья) и выйти.",
        )
        parser.add_argument(
            "--id",
            type=int,
            action="append",
            dest="ids",
            help="Только эти id статей (можно повторять).",
        )
        parser.add_argument(
            "--kind",
            choices=("all", "after_tilde", "mixed"),
            default="all",
            help="Фильтр вида находки.",
        )
        parser.add_argument(
            "--queue",
            choices=("homoglyph", "krl", "rus", "non_homoglyph", "all"),
            default="homoglyph",
            help=(
                "homoglyph|krl — карельский (кир.→лат.); "
                "rus|non_homoglyph — русский (лат.→кир.); all — всё."
            ),
        )
        parser.add_argument(
            "--order",
            choices=("word", "id"),
            default="word",
        )

    def _ask(self, prompt):
        sys.stdout.write(prompt)
        sys.stdout.flush()
        raw = sys.stdin.buffer.readline()
        if raw == b"":
            raise EOFError
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        line = "".join(
            ch for ch in line if ch == "\t" or (ord(ch) >= 32 and ch != "\ufffd")
        )
        return line

    def _collect(self, opts):
        rows, _letters = scan_cyrillic_in_html()
        if opts["ids"]:
            id_set = set(opts["ids"])
            rows = [r for r in rows if r["article_id"] in id_set]
        if opts["kind"] != "all":
            rows = [r for r in rows if r["kind"] == opts["kind"]]
        queue = opts["queue"]
        if queue in ("homoglyph", "krl"):
            rows = [r for r in rows if r["direction"] == "krl"]
        elif queue in ("rus", "non_homoglyph"):
            rows = [r for r in rows if r["direction"] == "rus"]
        if opts["order"] == "word":
            rows.sort(key=lambda r: ((r.get("word") or "").lower(), r["article_id"]))
        else:
            rows.sort(key=lambda r: (r["article_id"], r["offset"]))
        if opts["limit"]:
            rows = rows[: opts["limit"]]
        return rows

    def _show_item(self, idx, total, article, hit, proposed):
        direction = hit.get("direction", "?")
        label = (
            "krl: кир→лат"
            if direction == "krl"
            else "rus: лат→кир" if direction == "rus" else direction
        )
        self.stdout.write("\n" + "=" * 72)
        self.stdout.write(
            f"[{idx}/{total}]  id={article.id}  {article.word}  "
            f"{hit['kind']}  ({label})"
        )
        self.stdout.write("-" * 72)
        self.stdout.write(article.article_html or "(html пуст)")
        self.stdout.write("-" * 72)
        self.stdout.write(f"фрагмент:   {hit['value']!r}")
        self.stdout.write(f"символы:    {hit['chars']}")
        self.stdout.write(f"предложено: {hit['suggested']!r}")
        n = (article.article_html or "").count(hit["value"])
        if n > 1:
            self.stdout.write(f"(вхождений в HTML: {n} — заменится первое)")
        if hit["suggested"] == hit["value"]:
            self.stdout.write(
                self.style.WARNING(
                    "Предложение совпадает с исходным — пропуск/правка вручную."
                )
            )
        self.stdout.write("Предложение (HTML):")
        self.stdout.write(proposed if proposed is not None else "(замена невозможна)")
        self.stdout.write("-" * 72)

    def _dry_run(self, items):
        for idx, hit in enumerate(items, start=1):
            art = Article.objects.filter(pk=hit["article_id"]).first()
            if not art:
                continue
            proposed = apply_token_fix(
                art.article_html or "", hit["value"], hit["suggested"]
            )
            self._show_item(idx, len(items), art, hit, proposed)

    def _save(self, article, new_html):
        old = article.article_html
        with transaction.atomic():
            article.article_html = new_html
            article.save(update_fields=["article_html"])
        return old

    def _undo(self, payload):
        if not payload:
            return
        Article.objects.filter(pk=payload["article_id"]).update(
            article_html=payload["old_html"]
        )

    def _summary(self, done, skipped):
        self.stdout.write(
            self.style.SUCCESS(f"Итог: HTML обновлён — {done}, пропущено — {skipped}.")
        )

    def _read_cmd(self, prompt, done, skipped):
        try:
            line = self._ask(prompt)
        except (EOFError, KeyboardInterrupt):
            self.stdout.write("\nВыход.")
            self._summary(done, skipped)
            return None
        return line.strip()

    def _loop(self, items):
        total = len(items)
        done = skipped = 0
        last_undo = None
        self.stdout.write(
            "y — принять замену, пусто — пропуск, u — отмена последнего, q — выход."
        )
        for idx, hit in enumerate(items, start=1):
            article = Article.objects.filter(pk=hit["article_id"]).first()
            if not article:
                continue
            html = article.article_html or ""
            # Still a leak with this exact fragment?
            still = [
                h
                for h in find_html_cyrillic_leaks(html, article.id)
                if h["value"] == hit["value"]
            ]
            if not still:
                continue
            proposed = apply_token_fix(html, hit["value"], hit["suggested"])
            if proposed is None:
                skipped += 1
                self.stdout.write(
                    f"\n[{idx}/{total}] id={article.id} {article.word}: "
                    f"фрагмент {hit['value']!r} в HTML не найден — пропуск."
                )
                continue
            while True:
                self._show_item(idx, total, article, hit, proposed)
                cmd = self._read_cmd(
                    "y=принять / пусто=пропуск / u / q: ",
                    done,
                    skipped,
                )
                if cmd is None:
                    return
                low = cmd.lower()
                if low == "q":
                    self.stdout.write("Выход по 'q'.")
                    self._summary(done, skipped)
                    return
                if low == "u":
                    if last_undo:
                        self._undo(last_undo)
                        self.stdout.write(
                            self.style.WARNING("Последнее сохранение отменено.")
                        )
                        last_undo = None
                    else:
                        self.stdout.write("Отменять нечего.")
                    # refresh article/proposed after undo
                    article.refresh_from_db()
                    proposed = apply_token_fix(
                        article.article_html or "", hit["value"], hit["suggested"]
                    )
                    continue
                if cmd == "":
                    skipped += 1
                    self.stdout.write("Пропущено.")
                    break
                if low == "y":
                    if proposed is None:
                        self.stdout.write("Нечего сохранять.")
                        continue
                    old = self._save(article, proposed)
                    last_undo = {
                        "article_id": article.id,
                        "old_html": old,
                    }
                    done += 1
                    self.stdout.write(self.style.SUCCESS("HTML сохранён."))
                    break
                self.stdout.write("Неизвестная команда.")
        self.stdout.write("\nСписок закончился.")
        self._summary(done, skipped)

    def handle(self, *args, **opts):
        items = self._collect(opts)
        self.stdout.write(
            f"Очередь: {len(items)} " f"(kind={opts['kind']}, queue={opts['queue']})"
        )
        if not items:
            self.stdout.write("Пусто.")
            return
        if opts["dry_run"]:
            self._dry_run(items)
            return
        if not sys.stdin.isatty():
            self.stderr.write(
                "Нужен интерактивный TTY (docker exec -it …). "
                "Или --dry-run, чтобы только посмотреть очередь."
            )
            return
        self._loop(items)
