from collections import defaultdict

from django.core.management.base import BaseCommand

from dict.models import Article, ArticleIndexWord
from dict.see_audit import classify_html

BUCKETS = (
    "canon",
    "no_period",
    "mixed_script",
    "spaced",
    "bare",
    "comma_list",
    "deriv_tagged",
    "deriv_loose",
)


class Command(BaseCommand):
    help = (
        "Инвентаризация «см./ср.» и дериваций «от» в article_html "
        "(статьи + аддендумы). Только отчёт, ничего не пишет."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--examples",
            type=int,
            default=5,
            help="Сколько примеров показать на корзину (по умолчанию 5).",
        )

    def handle(self, *args, **options):
        n_ex = options["examples"]
        known = {
            w.lower()
            for w in ArticleIndexWord.objects.exclude(word=None).values_list(
                "word", flat=True
            )
            if w
        }
        known |= {
            w.lower()
            for w in Article.objects.values_list("word", flat=True)
            if w
        }

        hits = {k: 0 for k in BUCKETS}
        articles = {k: set() for k in BUCKETS}
        unresolved = 0
        unresolved_arts = set()
        examples = defaultdict(list)
        scanned = 0

        qs = Article.objects.prefetch_related("additions").iterator(chunk_size=200)
        for art in qs:
            scanned += 1
            blobs = [art.article_html or ""]
            blobs.extend(add.article_html or "" for add in art.additions.all())
            merged = {
                k: []
                for k in list(BUCKETS) + ["lemmas"]
            }
            for html in blobs:
                c = classify_html(html)
                for k in BUCKETS:
                    merged[k].extend(c[k])
                merged["lemmas"].extend(c["lemmas"])

            for k in BUCKETS:
                if merged[k]:
                    hits[k] += len(merged[k])
                    articles[k].add(art.pk)
                    if len(examples[k]) < n_ex:
                        examples[k].append((art.pk, art.word, merged[k][0]))

            for lemma, _src in merged["lemmas"]:
                if lemma.lower() not in known:
                    unresolved += 1
                    unresolved_arts.add(art.pk)

        self.stdout.write(f"Статей просмотрено: {scanned}")
        self.stdout.write("")
        self.stdout.write("Корзина                              хитов   статей")
        rows = [
            ("канон <i>см.|ср.</i> + лемма", "canon"),
            ("в <i> нет точки", "no_period"),
            ("латиница в маркере", "mixed_script"),
            ("пробелы внутри <i>", "spaced"),
            ("маркер без <i> (перед латиницей)", "bare"),
            ("список лемм через запятую", "comma_list"),
            ("<i>freq|caus|mom|refl</i> от lemma", "deriv_tagged"),
            ("прочее «от lemma»", "deriv_loose"),
        ]
        for title, key in rows:
            self.stdout.write(
                f"  {title:<36} {hits[key]:6d}  {len(articles[key]):6d}"
            )
        self.stdout.write(
            f"  {'лемма не в индексе заголовков':<36} {unresolved:6d}  "
            f"{len(unresolved_arts):6d}"
        )

        crooked = (
            articles["no_period"]
            | articles["mixed_script"]
            | articles["spaced"]
            | articles["bare"]
        )
        self.stdout.write("")
        self.stdout.write(
            f"Статей с кривым маркером см/ср (без канона/списков/от): "
            f"{len(crooked)}"
        )

        if n_ex:
            self.stdout.write("")
            self.stdout.write("Примеры:")
            for title, key in rows:
                if not examples[key]:
                    continue
                self.stdout.write(f"  [{key}] {title}")
                for pk, word, rec in examples[key]:
                    span = rec.get("span") or rec.get("inner") or rec.get("lemmas")
                    self.stdout.write(f"    #{pk} {word}: {span}")
