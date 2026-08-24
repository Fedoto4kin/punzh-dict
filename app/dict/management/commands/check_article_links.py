from django.core.management.base import BaseCommand

from dict.models import Article, ArticleLink
from dict.see_audit import html_see_lemmas, lookup_articles, scan_see_links


class Command(BaseCommand):
    help = (
        "Сверка HTML «см./ср.» с ArticleLink. Только отчёт. "
        "A — лемма в тексте, связи нет; B — связь есть, леммы в HTML нет; "
        "цель не та — однозначный резолв не совпадает с to_article; "
        "не резолвится / омоним."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--examples",
            type=int,
            default=8,
            help="Примеров на корзину (по умолчанию 8).",
        )
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **opts):
        n_ex = opts["examples"]
        qs = Article.objects.all().order_by("word")
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        links_by_from = {}
        for link in ArticleLink.objects.select_related("to_article").iterator():
            links_by_from.setdefault(link.from_article_id, []).append(link)

        missing = []  # A
        extra = []  # B
        wrong = []
        unresolved = []
        ambiguous = []
        multi_gap = []  # список лемм, не все цели в ArticleLink
        scanned = 0

        for art in qs.iterator(chunk_size=200):
            scanned += 1
            html = art.article_html or ""
            lemmas = html_see_lemmas(html)
            outgoing = links_by_from.get(art.id, [])
            linked_ids = {lnk.to_article_id for lnk in outgoing}
            scan = scan_see_links(art, outgoing)

            if len(lemmas) > 1:
                covered = []
                open_lemmas = []
                for lemma in lemmas:
                    found = lookup_articles(lemma, art.id)
                    ids = {a.id for a in found}
                    if ids & linked_ids:
                        covered.append(lemma)
                    else:
                        open_lemmas.append(lemma)
                if open_lemmas:
                    multi_gap.append((art, lemmas, covered, open_lemmas, outgoing))

            for row in scan["unique_missing"]:
                missing.append((art, row["lemma"], row["target"]))
            for row in scan["unresolved"]:
                unresolved.append((art, row["lemma"]))
            for row in scan["homonym"]:
                ambiguous.append((art, row["lemma"], row["found"]))
            for lnk in scan["extra"]:
                extra.append((art, lnk))
            for lemma in lemmas:
                found = lookup_articles(lemma, art.id)
                if len(found) != 1:
                    continue
                tgt = found[0]
                if tgt.id in linked_ids:
                    continue
                if linked_ids:
                    wrong.append((art, lemma, tgt, outgoing))

        def show(title, rows, fmt):
            self.stdout.write(f"{title}: {len(rows)}")
            for row in rows[:n_ex]:
                self.stdout.write("  " + fmt(row))

        self.stdout.write(f"Статей просмотрено: {scanned}")
        show(
            "A  в HTML есть лемма, ArticleLink нет (однозначная цель)",
            missing,
            lambda r: f"#{r[0].id} {r[0].word}  «{r[1]}» → #{r[2].id} {r[2].word}",
        )
        show(
            "список см./ср. из нескольких лемм, не все связаны",
            multi_gap,
            lambda r: (
                f"#{r[0].id} {r[0].word}  леммы: {', '.join(r[1])}; "
                f"есть связь: {', '.join(r[2]) or '—'}; "
                f"нет: {', '.join(r[3])}; "
                f"сейчас: "
                + (
                    ", ".join(f"#{x.to_article_id}" for x in r[4])
                    if r[4]
                    else "нет связей"
                )
            ),
        )
        show(
            "B  ArticleLink есть, в HTML этой леммы нет",
            extra,
            lambda r: (
                f"#{r[0].id} {r[0].word} → #{r[1].to_article_id} {r[1].to_article.word}"
            ),
        )
        # wrong overlaps missing when there are other links; report distinct
        wrong_only = [
            w
            for w in wrong
            if not any(w[0].id == m[0].id and w[1] == m[1] for m in missing)
        ]
        show(
            "цель не та (есть другие связи, однозначный резолв другой)",
            wrong_only,
            lambda r: (
                f"#{r[0].id} {r[0].word}  «{r[1]}» должно быть "
                f"#{r[2].id} {r[2].word}; сейчас: "
                + ", ".join(f"#{x.to_article_id}" for x in r[3])
            ),
        )
        show(
            "лемма не резолвится",
            unresolved,
            lambda r: f"#{r[0].id} {r[0].word}  «{r[1]}»",
        )
        show(
            "омоним, ни одна цель не связана",
            ambiguous,
            lambda r: (
                f"#{r[0].id} {r[0].word}  «{r[1]}»  кандидаты: "
                + ", ".join(f"#{a.id}" for a in r[2][:5])
            ),
        )
