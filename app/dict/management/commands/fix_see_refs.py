import sys

from django.core.management.base import BaseCommand
from django.db import transaction

from dict.models import Article, ArticleLink
from dict.see_audit import classify_html, is_crooked, lookup_articles, propose_html_fix


class Command(BaseCommand):
    help = (
        "Интерактивная правка кривых «см./ср.» в HTML и создание ArticleLink. "
        "По умолчанию очередь — кривой маркер (без <i>, точки, латиница). "
        "--comma: списки лемм через запятую без полного набора связей. "
        "--apply-unique: создать однозначные связи без вопросов. "
        "Команды: пустая строка — пропуск; y — принять HTML и связь; "
        "h — только HTML; t <id|слово> — цель связи; u — отмена последнего "
        "сохранения; q — выход. "
        "На проде: docker compose -f docker-compose.internal.yml exec django "
        "python manage.py fix_see_refs  (нужен TTY: exec без -T)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Не больше N статей за сессию.",
        )
        parser.add_argument(
            "--order",
            choices=["word", "id"],
            default="word",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать предложения и выйти, ничего не писать.",
        )
        parser.add_argument(
            "--id",
            type=int,
            action="append",
            dest="ids",
            help="Только эти id (можно повторять).",
        )
        parser.add_argument(
            "--comma",
            action="store_true",
            help=(
                "Очередь — канонические «см./ср.» со списком лемм через запятую, "
                "у которых не все ArticleLink ещё есть. HTML обычно не трогаем."
            ),
        )
        parser.add_argument(
            "--apply-unique",
            action="store_true",
            help=(
                "Без вопросов создать связи для однозначно найденных лемм "
                "(неоднозначные пропускаются). Удобно с --comma."
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

    def _lemmas(self, html):
        c = classify_html(html)
        seen = []
        for lemma, src in c["lemmas"]:
            if src in ("deriv", "deriv_loose"):
                continue
            if lemma not in seen:
                seen.append(lemma)
        return seen

    def _existing_to_ids(self, article_id):
        return set(
            ArticleLink.objects.filter(from_article_id=article_id).values_list(
                "to_article_id", flat=True
            )
        )

    def _gap(self, article):
        """Недостающие однозначные цели и нерезолвнувшиеся леммы."""
        lemmas = self._lemmas(propose_html_fix(article.article_html or ""))
        existing = self._existing_to_ids(article.id)
        unique_missing = []
        unresolved = []
        seen = set()
        for lemma in lemmas:
            found = self._lookup(lemma, article.id)
            if len(found) == 1:
                tgt = found[0]
                if tgt.id not in existing and tgt.id not in seen:
                    unique_missing.append(tgt)
                    seen.add(tgt.id)
            else:
                unresolved.append((lemma, found))
        return unique_missing, unresolved

    def _collect_ids(self, opts):
        qs = Article.objects.all()
        if opts["ids"]:
            qs = qs.filter(pk__in=opts["ids"])
        qs = qs.order_by("word" if opts["order"] == "word" else "id")
        ids = []
        comma = opts["comma"]
        for art in qs.only("id", "article_html", "word").iterator(chunk_size=200):
            html = art.article_html or ""
            if comma:
                if not classify_html(html)["comma_list"]:
                    continue
                unique_missing, unresolved = self._gap(art)
                if unique_missing or unresolved:
                    ids.append(art.id)
            elif is_crooked(html):
                ids.append(art.id)
        if opts["limit"]:
            ids = ids[: opts["limit"]]
        return ids

    def _save(self, article, new_html, targets, html_only):
        old_html = article.article_html
        created_link_ids = []
        with transaction.atomic():
            if new_html != old_html:
                Article.objects.filter(pk=article.pk).update(article_html=new_html)
            if not html_only:
                for tgt in targets:
                    obj, created = ArticleLink.objects.get_or_create(
                        from_article=article, to_article=tgt
                    )
                    if created:
                        created_link_ids.append(obj.id)
        article.article_html = new_html
        return old_html, created_link_ids

    def _undo(self, article_id, old_html, created_link_ids):
        Article.objects.filter(pk=article_id).update(article_html=old_html)
        if created_link_ids:
            ArticleLink.objects.filter(id__in=created_link_ids).delete()

    def handle(self, *args, **opts):
        comma = opts["comma"]
        ids = self._collect_ids(opts)
        total = len(ids)
        if not total:
            msg = (
                "Списков через запятую без полного набора связей нет."
                if comma
                else "Кривых «см./ср.» нет."
            )
            self.stdout.write(self.style.SUCCESS(msg))
            return

        label = "списков через запятую" if comma else "кривых маркеров"
        self.stdout.write(
            self.style.WARNING(
                f"{label.capitalize()}: {total}. "
                f"Пусто — пропуск, y — HTML+связь, h — только HTML, "
                f"t <id|слово> — цель, u — отмена, q — выход."
            )
        )

        if opts["dry_run"]:
            for aid in ids:
                art = Article.objects.get(pk=aid)
                proposed = propose_html_fix(art.article_html or "")
                lemmas = self._lemmas(proposed)
                existing = self._existing_to_ids(art.id)
                self.stdout.write("\n" + "=" * 72)
                self.stdout.write(f"id={art.id}  {art.word}")
                if not comma:
                    self.stdout.write(f"было: {art.article_html}")
                    self.stdout.write(f"станет: {proposed}")
                else:
                    self.stdout.write(art.article_html or "")
                for lemma in lemmas:
                    found = self._lookup(lemma, art.id)
                    if len(found) == 1:
                        t = found[0]
                        flag = "уже есть" if t.id in existing else "создать"
                        self.stdout.write(
                            f"  связь: {lemma} -> #{t.id} {t.word}  [{flag}]"
                        )
                    elif not found:
                        self.stdout.write(f"  связь: {lemma} -> НЕ НАЙДЕНА")
                    else:
                        self.stdout.write(
                            f"  связь: {lemma} -> {len(found)} кандидатов"
                        )
            return

        if opts["apply_unique"]:
            done_links = 0
            skipped = 0
            for aid in ids:
                article = Article.objects.get(pk=aid)
                unique_missing, unresolved = self._gap(article)
                if unique_missing:
                    proposed = propose_html_fix(article.article_html or "")
                    _, link_ids = self._save(
                        article,
                        proposed,
                        unique_missing,
                        html_only=False,
                    )
                    done_links += len(link_ids)
                    self.stdout.write(
                        f"#{article.id} {article.word}: +{len(link_ids)} связей"
                    )
                if unresolved:
                    skipped += 1
                    names = ", ".join(l for l, _ in unresolved)
                    self.stdout.write(
                        f"#{article.id} {article.word}: пропуск неоднозначных: {names}"
                    )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Итог: связей создано — {done_links}, "
                    f"статей с неоднозначными леммами — {skipped}."
                )
            )
            return

        done_html = 0
        done_links = 0
        skipped = 0
        last_undo = None

        for idx, aid in enumerate(ids, start=1):
            try:
                article = Article.objects.get(pk=aid)
            except Article.DoesNotExist:
                continue
            if not comma and not is_crooked(article.article_html or ""):
                continue

            override = None
            while True:
                proposed = propose_html_fix(article.article_html or "")
                lemmas = self._lemmas(proposed)
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
                for lemma in lemmas:
                    found = self._lookup(lemma, article.id)
                    if len(found) == 1:
                        unique_targets.append(found[0])
                        self.stdout.write(
                            f"цель «{lemma}»: #{found[0].id} {found[0].word}"
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

                try:
                    line = self._ask(
                        "y=принять / h=только html / t цель / пусто=пропуск / u / q: "
                    )
                except (EOFError, KeyboardInterrupt):
                    self.stdout.write("\nВыход.")
                    self._summary(done_html, done_links, skipped)
                    return

                cmd = line.strip()
                low = cmd.lower()

                if low == "q":
                    self.stdout.write("Выход по 'q'.")
                    self._summary(done_html, done_links, skipped)
                    return

                if low == "u":
                    if last_undo:
                        self._undo(*last_undo)
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
                    old_html, link_ids = self._save(
                        article, proposed, targets, html_only=html_only
                    )
                    last_undo = (article.id, old_html, link_ids)
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

    def _summary(self, done_html, done_links, skipped):
        self.stdout.write(
            self.style.SUCCESS(
                f"Итог: HTML обновлён — {done_html}, связей создано — {done_links}, "
                f"пропущено — {skipped}."
            )
        )
