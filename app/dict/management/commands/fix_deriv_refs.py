import sys

from django.core.management.base import BaseCommand, CommandError

from dict.models import Article, ArticleLink
from dict.see_audit import scan_deriv_links

QUEUES = ("unique", "unresolved", "homonym")


class Command(BaseCommand):
    help = (
        "Связи «от X» (kind=deriv): HTML не меняет. "
        "--apply-unique: однозначные цели без вопросов. "
        "--queue homonym|unresolved: t <id>, пусто — пропуск, u — отмена, q — выход."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument(
            "--order",
            choices=["word", "id"],
            default="word",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать очередь и выйти, ничего не писать.",
        )
        parser.add_argument(
            "--id",
            type=int,
            action="append",
            dest="ids",
            help="Только эти id статей (можно повторять).",
        )
        parser.add_argument(
            "--queue",
            choices=("homonym", "unresolved"),
            default=None,
            help="Интерактивная очередь (по умолчанию homonym).",
        )
        parser.add_argument(
            "--apply-unique",
            action="store_true",
            help="Без вопросов создать однозначные deriv-связи.",
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

    def _resolve_queue(self, opts):
        if opts["apply_unique"]:
            return "unique"
        return opts["queue"] or "homonym"

    def _links_map(self):
        m = {}
        for lnk in ArticleLink.objects.select_related("to_article").iterator():
            m.setdefault(lnk.from_article_id, []).append(lnk)
        return m

    def _articles_qs(self, opts):
        qs = Article.objects.all()
        if opts["ids"]:
            qs = qs.filter(pk__in=opts["ids"])
        return qs.order_by("word" if opts["order"] == "word" else "id")

    def _collect(self, opts, queue):
        links = self._links_map()
        items = []
        wrong_kind = []
        for art in (
            self._articles_qs(opts)
            .only("id", "word", "article_html")
            .iterator(chunk_size=200)
        ):
            outgoing = links.get(art.id, [])
            scan = scan_deriv_links(art, outgoing)
            if queue == "unique":
                seen = set()
                for row in scan["unique_missing"]:
                    tid = row["target"].id
                    if tid in seen:
                        continue
                    seen.add(tid)
                    items.append(
                        {
                            "kind": "unique",
                            "article_id": art.id,
                            "lemma": row["lemma"],
                            "target_id": tid,
                        }
                    )
                for row in scan["wrong_kind"]:
                    wrong_kind.append(
                        {
                            "article_id": art.id,
                            "lemma": row["lemma"],
                            "target_id": row["target"].id,
                        }
                    )
            elif queue == "unresolved":
                for row in scan["unresolved"]:
                    items.append(
                        {
                            "kind": "unresolved",
                            "article_id": art.id,
                            "lemma": row["lemma"],
                        }
                    )
            elif queue == "homonym":
                for row in scan["homonym"]:
                    items.append(
                        {
                            "kind": "homonym",
                            "article_id": art.id,
                            "lemma": row["lemma"],
                            "found_ids": [a.id for a in row["found"]],
                        }
                    )
        if opts["limit"]:
            items = items[: opts["limit"]]
        if queue == "unique":
            return items, wrong_kind
        return items

    def _warn_wrong_kind(self, rows):
        for row in rows:
            article = Article.objects.filter(pk=row["article_id"]).first()
            target = Article.objects.filter(pk=row["target_id"]).first()
            if not article or not target:
                continue
            self.stdout.write(
                self.style.WARNING(
                    f"#{article.id} {article.word}: «{row['lemma']}» → "
                    f"#{target.id} — связь есть, kind не deriv (пропуск)"
                )
            )

    def _create_link(self, from_id, to_id):
        existing = ArticleLink.objects.filter(
            from_article_id=from_id, to_article_id=to_id
        ).first()
        if existing:
            if existing.kind == ArticleLink.KIND_DERIV:
                return None, "exists"
            return None, "wrong_kind"
        obj = ArticleLink.objects.create(
            from_article_id=from_id,
            to_article_id=to_id,
            kind=ArticleLink.KIND_DERIV,
        )
        return obj.id, "created"

    def _undo(self, rec):
        if rec["kind"] == "create_links":
            ArticleLink.objects.filter(id__in=rec["ids"]).delete()

    def _create_unique_links(self, items):
        done = skipped_exist = skipped_wrong = 0
        for item in items:
            article = Article.objects.filter(pk=item["article_id"]).first()
            target = Article.objects.filter(pk=item["target_id"]).first()
            if not article or not target:
                continue
            lid, status = self._create_link(article.id, target.id)
            if status == "created":
                done += 1
                self.stdout.write(
                    f"#{article.id} {article.word}: «{item['lemma']}» → "
                    f"#{target.id} {target.word}"
                )
            elif status == "exists":
                skipped_exist += 1
            else:
                skipped_wrong += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"#{article.id} {article.word}: «{item['lemma']}» → "
                        f"#{target.id} — связь есть, kind не deriv (пропуск)"
                    )
                )
        return done, skipped_exist, skipped_wrong

    def handle(self, *args, **opts):
        queue = self._resolve_queue(opts)
        if opts["apply_unique"] and opts["queue"]:
            raise CommandError("--apply-unique несовместим с --queue.")

        items = self._collect(opts, queue)
        if queue == "unique":
            items, wrong_kind_rows = items
        else:
            wrong_kind_rows = []
        total = len(items)
        if not total and not (opts["apply_unique"] and wrong_kind_rows):
            empty = {
                "unique": "Однозначных дыр (корзина A) нет.",
                "unresolved": "Нерезолвящихся лемм нет.",
                "homonym": "Омонимов без связи нет.",
            }
            self.stdout.write(self.style.SUCCESS(empty[queue]))
            return

        if total:
            labels = {
                "unique": "однозначных дыр (A)",
                "unresolved": "нерезолвящихся лемм",
                "homonym": "омонимов без связи",
            }
            self.stdout.write(self.style.WARNING(f"Очередь {labels[queue]}: {total}."))

        if opts["dry_run"]:
            self._dry_run(items, queue)
            if wrong_kind_rows:
                self._warn_wrong_kind(wrong_kind_rows)
            return

        if opts["apply_unique"]:
            done, existed, wrong = self._create_unique_links(items)
            wrong += len(wrong_kind_rows)
            self._warn_wrong_kind(wrong_kind_rows)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Итог: связей создано — {done}, уже deriv — {existed}, "
                    f"пропущено (kind≠deriv) — {wrong}. HTML не меняли."
                )
            )
            return

        if queue == "unresolved":
            self._loop_pick(items, homonym=False)
            return
        self._loop_pick(items, homonym=True)

    def _dry_run(self, items, queue):
        for item in items:
            art = Article.objects.get(pk=item["article_id"])
            self.stdout.write("\n" + "=" * 72)
            self.stdout.write(f"id={art.id}  {art.word}")
            if item["kind"] == "unique":
                t = Article.objects.get(pk=item["target_id"])
                self.stdout.write(
                    f"  создать deriv: {item['lemma']} -> #{t.id} {t.word}"
                )
            elif item["kind"] == "unresolved":
                self.stdout.write(f"  не найдена: {item['lemma']}")
            else:
                ids = ", ".join(f"#{i}" for i in item.get("found_ids", []))
                self.stdout.write(f"  омоним «{item['lemma']}»: {ids}")

    def _summary(self, done_links, skipped):
        self.stdout.write(
            self.style.SUCCESS(
                f"Итог: связей создано — {done_links}, пропущено — {skipped}."
            )
        )

    def _read_cmd(self, prompt, done_links, skipped):
        try:
            line = self._ask(prompt)
        except (EOFError, KeyboardInterrupt):
            self.stdout.write("\nВыход.")
            self._summary(done_links, skipped)
            return None
        return line.strip()

    def _loop_pick(self, items, homonym):
        total = len(items)
        done_links = skipped = 0
        last_undo = None
        hint = (
            "t <id> = выбрать / пусто=пропуск / u / q: "
            if homonym
            else "t <id> = цель / пусто=пропуск / u / q: "
        )
        for idx, item in enumerate(items, start=1):
            article = Article.objects.filter(pk=item["article_id"]).first()
            if not article:
                continue
            self.stdout.write("\n" + "=" * 72)
            self.stdout.write(f"[{idx}/{total}]  id={article.id}  {article.word}")
            self.stdout.write(article.article_html or "(html пуст)")
            lemma = item["lemma"]
            if homonym:
                found = list(
                    Article.objects.filter(pk__in=item.get("found_ids") or []).order_by(
                        "word"
                    )
                )
                self.stdout.write(f"омоним «{lemma}», кандидаты:")
                for t in found[:20]:
                    self.stdout.write(f"    #{t.id}  {t.word}")
            else:
                self.stdout.write(f"лемма «{lemma}»: не найдена")
            while True:
                cmd = self._read_cmd(hint, done_links, skipped)
                if cmd is None:
                    return
                low = cmd.lower()
                if low == "q":
                    self.stdout.write("Выход по 'q'.")
                    self._summary(done_links, skipped)
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
                    continue
                if cmd == "":
                    skipped += 1
                    self.stdout.write("Пропущено.")
                    break
                if low.startswith("t "):
                    query = cmd[1:].strip()
                    if not query.isdigit():
                        self.stdout.write("Нужен числовой id статьи (t <id>).")
                        continue
                    tgt = Article.objects.filter(pk=int(query)).first()
                    if not tgt:
                        self.stdout.write("Не найдено.")
                        continue
                    if tgt.id == article.id:
                        self.stdout.write("Нельзя ссылаться на себя.")
                        continue
                    lid, status = self._create_link(article.id, tgt.id)
                    if status == "created":
                        last_undo = {"kind": "create_links", "ids": [lid]}
                        done_links += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"Связь deriv → #{tgt.id} {tgt.word}.")
                        )
                    elif status == "exists":
                        self.stdout.write("Связь deriv уже была.")
                    else:
                        self.stdout.write(
                            self.style.WARNING("Связь есть, kind не deriv — не меняем.")
                        )
                    break
                self.stdout.write("Неизвестная команда.")
        self.stdout.write("\nСписок закончился.")
        self._summary(done_links, skipped)
