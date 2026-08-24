from django.core.management.base import BaseCommand

from dict.models import ArticleLink
from dict.see_audit import article_index_words, html_see_mentions


def classify_mirror_pair(link_ab, link_ba):
    """
    Пара A→B и B→A. Что удалить, если в HTML нет зеркальной «см.».
    Возвращает (drop_ab, drop_ba) булевы.
    """
    a, b = link_ab.from_article, link_ab.to_article
    a_mentions_b = html_see_mentions(a.article_html or "", article_index_words(b))
    b_mentions_a = html_see_mentions(b.article_html or "", article_index_words(a))
    drop_ba = a_mentions_b and not b_mentions_a
    drop_ab = b_mentions_a and not a_mentions_b
    return drop_ab, drop_ba, a_mentions_b, b_mentions_a


class Command(BaseCommand):
    help = (
        "Найти зеркальные ArticleLink (A→B и B→A), где «см./ср.» есть "
        "только в одну сторону, и удалить лишнюю дугу. "
        "По умолчанию только отчёт; запись — с --apply. "
        "Взаимные отсылки в обоих HTML не трогаем. Пары без см. ни с одной "
        "стороны только печатаем."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Удалить лишние зеркала (без флага — dry-run).",
        )

    def handle(self, *args, **opts):
        seen = set()
        drop_ids = []
        mutual = 0
        orphan = 0
        n_pairs = 0

        qs = ArticleLink.objects.select_related("from_article", "to_article")
        by_pair = {}
        for link in qs.iterator(chunk_size=500):
            key = (link.from_article_id, link.to_article_id)
            by_pair[key] = link

        for (a_id, b_id), link_ab in by_pair.items():
            if a_id >= b_id:
                continue
            link_ba = by_pair.get((b_id, a_id))
            if link_ba is None:
                continue
            pair_key = (a_id, b_id)
            if pair_key in seen:
                continue
            seen.add(pair_key)
            n_pairs += 1
            drop_ab, drop_ba, a_ok, b_ok = classify_mirror_pair(link_ab, link_ba)
            a, b = link_ab.from_article, link_ab.to_article
            if drop_ba:
                drop_ids.append(link_ba.id)
                self.stdout.write(
                    f"лишнее B→A: #{b.id} {b.word} → #{a.id} {a.word} "
                    f"(см. только у A)"
                )
            if drop_ab:
                drop_ids.append(link_ab.id)
                self.stdout.write(
                    f"лишнее A→B: #{a.id} {a.word} → #{b.id} {b.word} "
                    f"(см. только у B)"
                )
            if a_ok and b_ok:
                mutual += 1
            if not a_ok and not b_ok:
                orphan += 1
                self.stdout.write(
                    f"пара без см. в HTML: #{a.id} {a.word} ↔ #{b.id} {b.word}"
                )

        self.stdout.write(
            f"Зеркальных пар: {n_pairs}; взаимных см.: {mutual}; "
            f"без см. в HTML: {orphan}; к удалению: {len(drop_ids)}."
        )
        if not drop_ids:
            return
        if not opts["apply"]:
            self.stdout.write("Dry-run. Для удаления: --apply")
            return
        deleted, _ = ArticleLink.objects.filter(id__in=drop_ids).delete()
        self.stdout.write(self.style.SUCCESS(f"Удалено связей: {deleted}."))
