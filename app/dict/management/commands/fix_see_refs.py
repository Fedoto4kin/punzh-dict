import sys

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dict.models import Article, ArticleLink
from dict.see_audit import (
    classify_html,
    html_see_lemmas,
    is_crooked,
    lookup_articles,
    propose_html_fix,
    scan_see_links,
)


QUEUES = ("crooked", "unique", "extra", "unresolved", "homonym", "comma")


class Command(BaseCommand):
    help = (
        "Правка «см./ср.»: HTML — источник истины, деривации «от» не трогаем. "
        "--queue unique --apply-unique: создать однозначные ArticleLink без "
        "вопросов и без правки HTML. Остальные очереди — по одной штуке: "
        "пусто — пропуск; extra: y — удалить связь; unresolved/homonym: "
        "t <id> — выбрать цель. Кривой маркер (--queue crooked, по умолчанию "
        "без --apply-unique): y — HTML+связь, h — только HTML. "
        "u — отмена последнего шага, q — выход. "
        "На проде: docker compose -f docker-compose.internal.yml exec django "
        "python manage.py fix_see_refs  (нужен TTY: exec без -T)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Не больше N элементов очереди за сессию.",
        )
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
            choices=QUEUES,
            default=None,
            help=(
                "Очередь: crooked (кривой маркер), unique (корзина A), extra (B), "
                "unresolved, homonym, comma (списки через запятую с дырами)."
            ),
        )
        parser.add_argument(
            "--comma",
            action="store_true",
            help="То же, что --queue comma.",
        )
        parser.add_argument(
            "--apply-unique",
            action="store_true",
            help=(
                "Без вопросов создать однозначные связи. HTML не меняет. "
                "Без --queue и без --comma — очередь unique (все A)."
            ),
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

    def _lookup(self, lemma, exclude_id):
        return lookup_articles(lemma, exclude_id)

    def _existing_to_ids(self, article_id):
        return set(
            ArticleLink.objects.filter(from_article_id=article_id).values_list(
                "to_article_id", flat=True
            )
        )

    def _resolve_queue(self, opts):
        if opts["queue"] and opts["comma"] and opts["queue"] != "comma":
            raise CommandError("Нельзя вместе --comma и --queue, кроме comma.")
        if opts["queue"]:
            return opts["queue"]
        if opts["comma"]:
            return "comma"
        if opts["apply_unique"]:
            return "unique"
        return "crooked"

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
        for art in (
            self._articles_qs(opts)
            .only("id", "word", "article_html")
            .iterator(chunk_size=200)
        ):
            html = art.article_html or ""
            outgoing = links.get(art.id, [])
            if queue == "crooked":
                if is_crooked(html):
                    items.append({"kind": "crooked", "article_id": art.id})
                continue
            scan = scan_see_links(art, outgoing)
            if queue == "comma":
                if not classify_html(html)["comma_list"]:
                    continue
                if scan["unique_missing"] or scan["unresolved"] or scan["homonym"]:
                    items.append({"kind": "comma", "article_id": art.id})
                continue
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
            elif queue == "extra":
                for lnk in scan["extra"]:
                    items.append(
                        {
                            "kind": "extra",
                            "article_id": art.id,
                            "link_id": lnk.id,
                            "to_id": lnk.to_article_id,
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
        return items

    def _save_html(self, article, new_html, targets, html_only):
        old_html = article.article_html
        created_link_ids = []
        with transaction.atomic():
            if new_html != old_html:
                Article.objects.filter(pk=article.pk).update(article_html=new_html)
            if not html_only:
                for tgt in targets:
                    obj, created = ArticleLink.objects.get_or_create(
                        from_article=article,
                        to_article=tgt,
                        defaults={"kind": ArticleLink.KIND_SEE},
                    )
                    if created:
                        created_link_ids.append(obj.id)
        article.article_html = new_html
        return old_html, created_link_ids

    def _create_link(self, from_id, to_id):
        obj, created = ArticleLink.objects.get_or_create(
            from_article_id=from_id,
            to_article_id=to_id,
            defaults={"kind": ArticleLink.KIND_SEE},
        )
        return obj.id if created else None

    def _delete_link(self, link_id):
        lnk = ArticleLink.objects.filter(pk=link_id).first()
        if not lnk:
            return None
        payload = {
            "from_article_id": lnk.from_article_id,
            "to_article_id": lnk.to_article_id,
        }
        lnk.delete()
        return payload

    def _undo(self, rec):
        kind = rec["kind"]
        if kind == "html_and_links":
            Article.objects.filter(pk=rec["article_id"]).update(
                article_html=rec["old_html"]
            )
            if rec["created_ids"]:
                ArticleLink.objects.filter(id__in=rec["created_ids"]).delete()
        elif kind == "create_links":
            ArticleLink.objects.filter(id__in=rec["ids"]).delete()
        elif kind == "delete_link":
            ArticleLink.objects.get_or_create(
                from_article_id=rec["from_article_id"],
                to_article_id=rec["to_article_id"],
                defaults={"kind": ArticleLink.KIND_SEE},
            )

    def _create_unique_links(self, items):
        done = 0
        skipped_exist = 0
        for item in items:
            article = Article.objects.filter(pk=item["article_id"]).first()
            target = Article.objects.filter(pk=item["target_id"]).first()
            if not article or not target:
                continue
            lid = self._create_link(article.id, target.id)
            if lid:
                done += 1
                self.stdout.write(
                    f"#{article.id} {article.word}: «{item['lemma']}» → "
                    f"#{target.id} {target.word}"
                )
            else:
                skipped_exist += 1
        return done, skipped_exist

    def handle(self, *args, **opts):
        queue = self._resolve_queue(opts)
        if opts["apply_unique"] and queue not in ("unique", "comma"):
            raise CommandError("--apply-unique только с очередью unique или comma.")

        items = self._collect(opts, queue)
        total = len(items)
        if not total:
            empty = {
                "crooked": "Кривых «см./ср.» нет.",
                "unique": "Однозначных дыр (корзина A) нет.",
                "extra": "Лишних связей (корзина B) нет.",
                "unresolved": "Нерезолвящихся лемм нет.",
                "homonym": "Омонимов без связи нет.",
                "comma": "Списков через запятую без полного набора связей нет.",
            }
            self.stdout.write(self.style.SUCCESS(empty[queue]))
            return

        labels = {
            "crooked": "кривых маркеров",
            "unique": "однозначных дыр (A)",
            "extra": "лишних связей (B)",
            "unresolved": "нерезолвящихся лемм",
            "homonym": "омонимов без связи",
            "comma": "списков через запятую",
        }
        self.stdout.write(self.style.WARNING(f"Очередь {labels[queue]}: {total}."))

        if opts["dry_run"]:
            self._dry_run(items, queue)
            return

        if opts["apply_unique"]:
            if queue == "comma":
                uniq = []
                for item in items:
                    art = Article.objects.get(pk=item["article_id"])
                    outgoing = list(
                        ArticleLink.objects.filter(
                            from_article_id=art.id
                        ).select_related("to_article")
                    )
                    seen = set()
                    for row in scan_see_links(art, outgoing)["unique_missing"]:
                        tid = row["target"].id
                        if tid in seen:
                            continue
                        seen.add(tid)
                        uniq.append(
                            {
                                "article_id": art.id,
                                "lemma": row["lemma"],
                                "target_id": tid,
                            }
                        )
                items = uniq
            done, existed = self._create_unique_links(items)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Итог: связей создано — {done}, уже были — {existed}. "
                    f"HTML не меняли."
                )
            )
            return

        if queue == "crooked":
            self._loop_crooked(items)
            return
        if queue == "comma":
            self._loop_comma(items)
            return
        if queue == "unique":
            self._loop_unique(items)
            return
        if queue == "extra":
            self._loop_extra(items)
            return
        if queue == "unresolved":
            self._loop_pick(items, homonym=False)
            return
        self._loop_pick(items, homonym=True)

    def _dry_run(self, items, queue):
        for item in items:
            if item["kind"] in ("crooked", "comma"):
                art = Article.objects.get(pk=item["article_id"])
                self.stdout.write("\n" + "=" * 72)
                self.stdout.write(f"id={art.id}  {art.word}")
                if item["kind"] == "crooked":
                    self.stdout.write(f"было: {art.article_html}")
                    self.stdout.write(
                        f"станет: {propose_html_fix(art.article_html or '')}"
                    )
                else:
                    self.stdout.write(art.article_html or "")
                outgoing = list(
                    ArticleLink.objects.filter(from_article_id=art.id).select_related(
                        "to_article"
                    )
                )
                scan = scan_see_links(art, outgoing)
                for row in scan["unique_missing"]:
                    t = row["target"]
                    self.stdout.write(f"  создать: {row['lemma']} -> #{t.id} {t.word}")
                for row in scan["unresolved"]:
                    self.stdout.write(f"  не найдена: {row['lemma']}")
                for row in scan["homonym"]:
                    self.stdout.write(
                        f"  омоним: {row['lemma']} ({len(row['found'])} шт.)"
                    )
                continue
            art = Article.objects.get(pk=item["article_id"])
            self.stdout.write("\n" + "=" * 72)
            self.stdout.write(f"id={art.id}  {art.word}")
            if item["kind"] == "unique":
                t = Article.objects.get(pk=item["target_id"])
                self.stdout.write(f"  создать: {item['lemma']} -> #{t.id} {t.word}")
            elif item["kind"] == "extra":
                t = Article.objects.filter(pk=item["to_id"]).first()
                tw = t.word if t else "?"
                self.stdout.write(f"  лишняя связь -> #{item['to_id']} {tw}")
            elif item["kind"] == "unresolved":
                self.stdout.write(f"  не найдена: {item['lemma']}")
            else:
                ids = ", ".join(f"#{i}" for i in item.get("found_ids", []))
                self.stdout.write(f"  омоним «{item['lemma']}»: {ids}")

    def _summary(self, done_html, done_links, skipped, deleted=0):
        parts = [
            f"HTML обновлён — {done_html}",
            f"связей создано — {done_links}",
            f"связей удалено — {deleted}",
            f"пропущено — {skipped}",
        ]
        self.stdout.write(self.style.SUCCESS("Итог: " + ", ".join(parts) + "."))

    def _read_cmd(self, prompt, done_html, done_links, skipped, deleted=0):
        try:
            line = self._ask(prompt)
        except (EOFError, KeyboardInterrupt):
            self.stdout.write("\nВыход.")
            self._summary(done_html, done_links, skipped, deleted)
            return None
        return line.strip()

    def _loop_unique(self, items):
        total = len(items)
        done_links = skipped = 0
        last_undo = None
        for idx, item in enumerate(items, start=1):
            article = Article.objects.filter(pk=item["article_id"]).first()
            target = Article.objects.filter(pk=item["target_id"]).first()
            if not article or not target:
                continue
            if ArticleLink.objects.filter(
                from_article=article, to_article=target
            ).exists():
                continue
            self.stdout.write("\n" + "=" * 72)
            self.stdout.write(f"[{idx}/{total}]  id={article.id}  {article.word}")
            self.stdout.write(article.article_html or "(html пуст)")
            self.stdout.write(
                f"создать связь «{item['lemma']}» → #{target.id} {target.word}"
            )
            while True:
                cmd = self._read_cmd(
                    "y=создать / пусто=пропуск / u / q: ",
                    0,
                    done_links,
                    skipped,
                )
                if cmd is None:
                    return
                low = cmd.lower()
                if low == "q":
                    self.stdout.write("Выход по 'q'.")
                    self._summary(0, done_links, skipped)
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
                if low == "y":
                    lid = self._create_link(article.id, target.id)
                    if lid:
                        last_undo = {"kind": "create_links", "ids": [lid]}
                        done_links += 1
                        self.stdout.write(self.style.SUCCESS("Связь создана."))
                    else:
                        self.stdout.write("Связь уже была.")
                    break
                self.stdout.write("Неизвестная команда.")
        self.stdout.write("\nСписок закончился.")
        self._summary(0, done_links, skipped)

    def _loop_extra(self, items):
        total = len(items)
        deleted = skipped = 0
        last_undo = None
        for idx, item in enumerate(items, start=1):
            article = Article.objects.filter(pk=item["article_id"]).first()
            lnk = (
                ArticleLink.objects.filter(pk=item["link_id"])
                .select_related("to_article")
                .first()
            )
            if not article or not lnk:
                continue
            self.stdout.write("\n" + "=" * 72)
            self.stdout.write(f"[{idx}/{total}]  id={article.id}  {article.word}")
            self.stdout.write(article.article_html or "(html пуст)")
            self.stdout.write(
                f"связь в БД, леммы в HTML нет: → "
                f"#{lnk.to_article_id} {lnk.to_article.word}"
            )
            while True:
                cmd = self._read_cmd(
                    "y=удалить связь / пусто=оставить / u / q: ",
                    0,
                    0,
                    skipped,
                    deleted,
                )
                if cmd is None:
                    return
                low = cmd.lower()
                if low == "q":
                    self.stdout.write("Выход по 'q'.")
                    self._summary(0, 0, skipped, deleted)
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
                    self.stdout.write("Оставлено.")
                    break
                if low == "y":
                    payload = self._delete_link(lnk.id)
                    if payload:
                        last_undo = {"kind": "delete_link", **payload}
                        deleted += 1
                        self.stdout.write(self.style.SUCCESS("Связь удалена."))
                    else:
                        self.stdout.write("Связи уже нет.")
                    break
                self.stdout.write("Неизвестная команда.")
        self.stdout.write("\nСписок закончился.")
        self._summary(0, 0, skipped, deleted)

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
                if not found:
                    found = self._lookup(lemma, article.id)
                self.stdout.write(f"омоним «{lemma}», кандидаты:")
                for t in found[:20]:
                    self.stdout.write(f"    #{t.id}  {t.word}")
            else:
                self.stdout.write(f"лемма «{lemma}»: не найдена")
            while True:
                cmd = self._read_cmd(hint, 0, done_links, skipped)
                if cmd is None:
                    return
                low = cmd.lower()
                if low == "q":
                    self.stdout.write("Выход по 'q'.")
                    self._summary(0, done_links, skipped)
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
                    if not query:
                        self.stdout.write("t <id>")
                        continue
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
                    lid = self._create_link(article.id, tgt.id)
                    if lid:
                        last_undo = {"kind": "create_links", "ids": [lid]}
                        done_links += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"Связь → #{tgt.id} {tgt.word}.")
                        )
                    else:
                        self.stdout.write("Связь уже была.")
                    break
                self.stdout.write("Неизвестная команда.")
        self.stdout.write("\nСписок закончился.")
        self._summary(0, done_links, skipped)

    def _loop_comma(self, items):
        total = len(items)
        done_links = skipped = 0
        last_undo = None
        for idx, item in enumerate(items, start=1):
            article = Article.objects.filter(pk=item["article_id"]).first()
            if not article:
                continue
            while True:
                outgoing = list(
                    ArticleLink.objects.filter(
                        from_article_id=article.id
                    ).select_related("to_article")
                )
                scan = scan_see_links(article, outgoing)
                self.stdout.write("\n" + "=" * 72)
                self.stdout.write(f"[{idx}/{total}]  id={article.id}  {article.word}")
                self.stdout.write(article.article_html or "(html пуст)")
                unique_targets = []
                for row in scan["unique_missing"]:
                    unique_targets.append(row["target"])
                    t = row["target"]
                    self.stdout.write(f"цель «{row['lemma']}»: #{t.id} {t.word}")
                for row in scan["unresolved"]:
                    self.stdout.write(f"цель «{row['lemma']}»: не найдена (t <id>)")
                for row in scan["homonym"]:
                    self.stdout.write(
                        f"цель «{row['lemma']}»: {len(row['found'])} вариантов:"
                    )
                    for t in row["found"][:10]:
                        self.stdout.write(f"    #{t.id}  {t.word}")
                cmd = self._read_cmd(
                    "y=однозначные связи / t <id> / пусто=пропуск / u / q: ",
                    0,
                    done_links,
                    skipped,
                )
                if cmd is None:
                    return
                low = cmd.lower()
                if low == "q":
                    self.stdout.write("Выход по 'q'.")
                    self._summary(0, done_links, skipped)
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
                        self.stdout.write("t <id>")
                        continue
                    tgt = Article.objects.filter(pk=int(query)).first()
                    if not tgt:
                        self.stdout.write("Не найдено.")
                        continue
                    lid = self._create_link(article.id, tgt.id)
                    if lid:
                        last_undo = {"kind": "create_links", "ids": [lid]}
                        done_links += 1
                        self.stdout.write(self.style.SUCCESS("Связь создана."))
                    continue
                if low == "y":
                    if not unique_targets:
                        self.stdout.write("Нет однозначных целей — t <id> или пропуск.")
                        continue
                    ids = []
                    for t in unique_targets:
                        lid = self._create_link(article.id, t.id)
                        if lid:
                            ids.append(lid)
                    if ids:
                        last_undo = {"kind": "create_links", "ids": ids}
                        done_links += len(ids)
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Связей создано: {len(ids)}. HTML не трогали."
                            )
                        )
                    else:
                        self.stdout.write("Новых связей нет.")
                    break
                self.stdout.write("Неизвестная команда.")
        self.stdout.write("\nСписок закончился.")
        self._summary(0, done_links, skipped)

    def _loop_crooked(self, items):
        ids = [item["article_id"] for item in items]
        total = len(ids)
        done_html = done_links = skipped = 0
        last_undo = None
        self.stdout.write(
            "Пусто — пропуск, y — HTML+связь, h — только HTML, "
            "t <id|слово> — цель, u — отмена, q — выход."
        )
        for idx, aid in enumerate(ids, start=1):
            try:
                article = Article.objects.get(pk=aid)
            except Article.DoesNotExist:
                continue
            if not is_crooked(article.article_html or ""):
                continue
            override = None
            while True:
                proposed = propose_html_fix(article.article_html or "")
                lemmas = html_see_lemmas(proposed)
                self.stdout.write("\n" + "=" * 72)
                self.stdout.write(f"[{idx}/{total}]  id={article.id}  {article.word}")
                self.stdout.write("-" * 72)
                self.stdout.write(article.article_html or "(html пуст)")
                self.stdout.write("-" * 72)
                self.stdout.write("Предложение:")
                self.stdout.write(proposed)
                self.stdout.write("-" * 72)
                unique_targets = []
                unresolved = 0
                existing = self._existing_to_ids(article.id)
                for lemma in lemmas:
                    found = self._lookup(lemma, article.id)
                    if len(found) == 1:
                        unique_targets.append(found[0])
                        flag = ""
                        if found[0].id in existing:
                            flag = " (уже есть)"
                        self.stdout.write(
                            f"цель «{lemma}»: #{found[0].id} {found[0].word}{flag}"
                        )
                    elif not found:
                        unresolved += 1
                        self.stdout.write(f"цель «{lemma}»: не найдена (t <id|слово>)")
                    else:
                        unresolved += 1
                        self.stdout.write(f"цель «{lemma}»: {len(found)} вариантов:")
                        for t in found[:10]:
                            self.stdout.write(f"    #{t.id}  {t.word}")
                if override is not None:
                    unique_targets.append(override)
                    self.stdout.write(f"цель вручную: #{override.id} {override.word}")
                by_id = {}
                for t in unique_targets:
                    by_id[t.id] = t
                unique_targets = list(by_id.values())
                cmd = self._read_cmd(
                    "y=принять / h=только html / t цель / пусто=пропуск / u / q: ",
                    done_html,
                    done_links,
                    skipped,
                )
                if cmd is None:
                    return
                low = cmd.lower()
                if low == "q":
                    self.stdout.write("Выход по 'q'.")
                    self._summary(done_html, done_links, skipped)
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
                if low.startswith("t ") or (
                    low.startswith("t") and len(low) > 1 and low[1] == " "
                ):
                    query = cmd[1:].strip()
                    if not query:
                        self.stdout.write("t <id или слово>")
                        continue
                    if query.isdigit():
                        tgt = Article.objects.filter(pk=int(query)).first()
                        found = [tgt] if tgt else []
                    else:
                        found = self._lookup(query, article.id)
                    if len(found) == 1:
                        override = found[0]
                        continue
                    if not found:
                        self.stdout.write("Не найдено.")
                    else:
                        for t in found[:10]:
                            self.stdout.write(f"    #{t.id}  {t.word}")
                    continue
                if low in ("y", "h"):
                    if low == "h":
                        targets, html_only = [], True
                    else:
                        targets, html_only = unique_targets, False
                        if not targets:
                            self.stdout.write(
                                "Нет однозначной цели — t <id> или h (только HTML)."
                            )
                            continue
                        if unresolved:
                            self.stdout.write(
                                f"Неразрешённых лемм: {unresolved} — "
                                f"связь только по однозначным (+ t)."
                            )
                    old_html, link_ids = self._save_html(
                        article, proposed, targets, html_only=html_only
                    )
                    last_undo = {
                        "kind": "html_and_links",
                        "article_id": article.id,
                        "old_html": old_html,
                        "created_ids": link_ids,
                    }
                    done_html += 1 if proposed != old_html else 0
                    done_links += len(link_ids)
                    msg = "HTML сохранён."
                    if link_ids:
                        msg += f" Связей создано: {len(link_ids)}."
                    elif html_only:
                        msg += " Связь не писали."
                    self.stdout.write(self.style.SUCCESS(msg))
                    break
                self.stdout.write("Неизвестная команда.")
        self.stdout.write("\nСписок закончился.")
        self._summary(done_html, done_links, skipped)
