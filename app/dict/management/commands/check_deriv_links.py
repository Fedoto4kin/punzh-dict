from django.core.management.base import BaseCommand

from dict.models import Article, ArticleLink
from dict.see_audit import scan_deriv_links


class Command(BaseCommand):
    help = (
        "Сверка дериваций «от X» в HTML с ArticleLink (kind=deriv). Только отчёт. "
        "A — однозначная цель, связи нет; омоним; не резолвится; "
        "цель связана, но kind не deriv."
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

        missing = []
        unresolved = []
        ambiguous = []
        wrong_kind = []
        satisfied = []
        stats = {
            "tagged": {"ok": 0, "hom": 0, "miss": 0, "already": 0, "wrong": 0},
            "loose": {"ok": 0, "hom": 0, "miss": 0, "already": 0, "wrong": 0},
        }
        scanned = 0

        for art in qs.iterator(chunk_size=200):
            scanned += 1
            outgoing = links_by_from.get(art.id, [])
            scan = scan_deriv_links(art, outgoing)

            for row in scan["unique_missing"]:
                missing.append((art, row))
                stats[row["source"]]["ok"] += 1
            for row in scan["unresolved"]:
                unresolved.append((art, row))
                stats[row["source"]]["miss"] += 1
            for row in scan["homonym"]:
                ambiguous.append((art, row))
                stats[row["source"]]["hom"] += 1
            for row in scan["wrong_kind"]:
                wrong_kind.append((art, row))
                stats[row["source"]]["wrong"] += 1
            for row in scan["already"]:
                satisfied.append((art, row))
                stats[row["source"]]["already"] += 1

        def show(title, rows, fmt):
            self.stdout.write(f"{title}: {len(rows)}")
            for row in rows[:n_ex]:
                self.stdout.write("  " + fmt(row))

        self.stdout.write(f"Статей просмотрено: {scanned}")
        self.stdout.write(
            f"tagged {stats['tagged']}  loose {stats['loose']}  "
            f"sum ok {stats['tagged']['ok'] + stats['loose']['ok']}"
        )
        show(
            "A  в HTML «от», однозначная цель, ArticleLink нет",
            missing,
            lambda r: (
                f"#{r[0].id} {r[0].word} [{r[1]['source']}] "
                f"«{r[1]['lemma']}» → #{r[1]['target'].id} {r[1]['target'].word}"
            ),
        )
        show(
            "омоним, ни одна цель не связана",
            ambiguous,
            lambda r: (
                f"#{r[0].id} {r[0].word} [{r[1]['source']}] "
                f"«{r[1]['lemma']}»  кандидаты: "
                + ", ".join(f"#{a.id}" for a in r[1]["found"][:5])
            ),
        )
        show(
            "лемма не резолвится",
            unresolved,
            lambda r: f"#{r[0].id} {r[0].word} [{r[1]['source']}]  «{r[1]['lemma']}»",
        )
        show(
            "связь есть, kind не deriv",
            wrong_kind,
            lambda r: (
                f"#{r[0].id} {r[0].word} [{r[1]['source']}] "
                f"«{r[1]['lemma']}» → #{r[1]['target'].id} "
                f"({r[1]['link'].kind})"
            ),
        )
        show(
            "уже deriv",
            satisfied,
            lambda r: (
                f"#{r[0].id} {r[0].word} [{r[1]['source']}] "
                f"→ #{r[1]['target'].id} {r[1]['target'].word}"
            ),
        )
