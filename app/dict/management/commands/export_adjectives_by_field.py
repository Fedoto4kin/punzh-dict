from collections import defaultdict

from django.core.management.base import BaseCommand

from dict.helpers import normalization, KRL_ABC
from dict.models import (
    Article,
    Tag,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleLink,
    SemanticField,
    ArticleSemanticField,
)


# Adjective помета. Confirmed: Tag id=13 ("adjectivum" / «имя прилагательное»).
# --tag-id is the exact, preferred selector; --pos (name substring) is a fallback.
DEFAULT_TAG_ID = 13
DEFAULT_POS = None

DEFAULT_OUT = "adjectives_by_field.md"


class Command(BaseCommand):
    help = (
        "Выгрузить все прилагательные (Article) с группировкой по смысловому "
        "полю в markdown. Формат: '### Поле', под ним определение, затем "
        "алфавитный список слов в НОРМАЛИЗОВАННОЙ орфографии. "
        "Нормализованная форма — это normalization(word_normalized or word), "
        "как в Article.__str__ (поле word_normalized — лишь «коррекция "
        "заголовка», сырьё для нормализации, а не готовая форма). "
        "Прилагательные-отсылки («см. X») своих полей не имеют — попадают под "
        "поля донора (транзитивно через linked_article / ArticleLink). "
        "Нераспределённые формы не теряются: уходят в секцию «Без поля». "
        "Сортировка — по алфавиту KRL_ABC, палатализация «’» в ключе игнорируется."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tag-id",
            type=int,
            default=DEFAULT_TAG_ID,
            help=f"ID тега прилагательного (по умолчанию {DEFAULT_TAG_ID} — adjectivum).",
        )
        parser.add_argument(
            "--pos",
            default=DEFAULT_POS,
            help="Запасной путь: подстрока в Tag.name (используется, только если задан).",
        )
        parser.add_argument(
            "--type",
            type=int,
            default=None,
            help="Опционально сузить поиск POS-пометы до Tag.type = N.",
        )
        parser.add_argument(
            "--out",
            default=DEFAULT_OUT,
            help=f"Путь к выходному .md (по умолчанию {DEFAULT_OUT}).",
        )
        parser.add_argument(
            "--list-tags",
            action="store_true",
            help="Показать теги-кандидаты на POS-помету и выйти (для сверки).",
        )

    # --- discovery -----------------------------------------------------------

    def _list_tags(self, type_filter):
        qs = Tag.objects.all().order_by("type", "sorting", "name")
        if type_filter is not None:
            qs = qs.filter(type=type_filter)
        self.stdout.write("Теги (id | type | name | tag):")
        for t in qs:
            self.stdout.write(f"  {t.id} | {t.type} | {t.name!r} | {t.tag!r}")

    # --- helpers -------------------------------------------------------------

    def _build_order(self):
        # Collation from the project's own alphabet. get_krl_abc() maps Ü→Y.
        abc = KRL_ABC.replace("Ü", "Y")
        order = {}
        for i, up in enumerate(abc):
            order.setdefault(up.lower(), i)
        return order

    def _sort_key(self, line):
        # Alphabetize by the base lemma only: strip translations (after ":")
        # and the header variant (after ","), lowercase, ignore palatalization.
        base = (line or "").split(":")[0].split(",")[0]
        base = base.replace("’", "").replace("'", "").strip().lower()
        big = len(self._order)
        return [self._order.get(ch, big) for ch in base]

    def _norm(self, article):
        # Normalized orthography = run the header through normalization(), using
        # the manual header correction when present. Guard so one malformed
        # header does not abort the whole export.
        header = article.word_normalized or article.word
        try:
            return normalization(header).strip()
        except Exception:
            self._norm_errors += 1
            return (article.word or "").strip()

    # --- main ----------------------------------------------------------------

    def handle(self, *args, **opts):
        if opts["list_tags"]:
            self._list_tags(opts["type"])
            return

        pos = opts["pos"]
        self._order = self._build_order()
        self._norm_errors = 0

        # 1) adjective tags — by exact id (preferred) or by name substring (fallback)
        if pos:
            tag_qs = Tag.objects.filter(name__icontains=pos)
        else:
            tag_qs = Tag.objects.filter(id=opts["tag_id"])
        if opts["type"] is not None:
            tag_qs = tag_qs.filter(type=opts["type"])
        tag_ids = list(tag_qs.values_list("id", flat=True))
        if not tag_ids:
            sel = f"name~{pos!r}" if pos else f"id={opts['tag_id']}"
            self.stderr.write(
                f"Тег прилагательного не найден ({sel}). "
                f"Запусти с --list-tags, чтобы увидеть реальные пометы."
            )
            return
        matched = ", ".join(sorted(tag_qs.values_list("name", flat=True)))
        self.stdout.write(f"POS-помета: {matched} (tag_id={tag_ids})")

        # 2) adjective articles (ids)
        adj_ids = set(
            ArticleIndexTag.objects.filter(tag_id__in=tag_ids)
            .values_list("article_id", flat=True)
            .distinct()
        )
        self.stdout.write(f"Прилагательных-статей: {len(adj_ids)}")
        if not adj_ids:
            return

        articles = {a.id: a for a in Article.objects.filter(id__in=adj_ids)}

        # 3) own semantic fields for the adjectives
        own = defaultdict(set)  # article_id -> {field_name}
        for aid, fname in ArticleSemanticField.objects.filter(
            article_id__in=adj_ids
        ).values_list("article_id", "field__name"):
            own[aid].add(fname)

        # 4) donor resolution — for EVERY adjective that carries a «см.» link.
        # A «см.» reference is a property of the article itself (linked_article),
        # independent of whether the article was also classified into fields.
        donor_of = {}  # article_id -> donor_article_id

        # 4a) direct pointer Article.linked_article (the model's «см.» FK)
        for aid in adj_ids:
            art = articles.get(aid)
            did = getattr(art, "linked_article_id", None)
            if did:
                donor_of[aid] = did

        # 4b) ArticleLink (from_article «см.» to_article) for the rest
        still = [aid for aid in adj_ids if aid not in donor_of]
        if still:
            for src, dst in ArticleLink.objects.filter(
                from_article_id__in=still
            ).values_list("from_article_id", "to_article_id"):
                donor_of.setdefault(src, dst)

        # 4c) donor fields + donor normalized word (for placement and the note).
        donor_ids = set(donor_of.values())
        donor_fields = defaultdict(set)
        donor_word = {}
        if donor_ids:
            for aid, fname in ArticleSemanticField.objects.filter(
                article_id__in=donor_ids
            ).values_list("article_id", "field__name"):
                donor_fields[aid].add(fname)
            for a in Article.objects.filter(id__in=donor_ids):
                donor_word[a.id] = self._norm(a)

        # 4d) reverse inheritance. For adjectives that would otherwise be
        # field-less (no own fields AND no fields via an outgoing «см.»), inherit
        # fields from the articles that point TO them (incoming «см.»). This lets
        # an empty variant form (e.g. avamieline, no own translation, never
        # classified) fall into the category of the headword that references it
        # (avomieline). No «см.» note is added here: the link is incoming — this
        # article is the target of a reference, not a reference itself.
        fieldless = []
        for aid in adj_ids:
            if own.get(aid):
                continue
            did = donor_of.get(aid)
            if did and donor_fields.get(did):
                continue
            fieldless.append(aid)

        rev_fields = defaultdict(set)  # article_id -> {field_name} from incomers
        if fieldless:
            src_of = defaultdict(set)  # target_id -> {source article id}
            # incoming via Article.linked_article (reverse FK)
            for src, tgt in Article.objects.filter(
                linked_article_id__in=fieldless
            ).values_list("id", "linked_article_id"):
                src_of[tgt].add(src)
            # incoming via ArticleLink (to_article is our target)
            for src, tgt in ArticleLink.objects.filter(
                to_article_id__in=fieldless
            ).values_list("from_article_id", "to_article_id"):
                src_of[tgt].add(src)

            all_src = set()
            for s in src_of.values():
                all_src |= s
            src_fields = defaultdict(set)
            if all_src:
                for sid, fname in ArticleSemanticField.objects.filter(
                    article_id__in=all_src
                ).values_list("article_id", "field__name"):
                    src_fields[sid].add(fname)
            for tgt, sources in src_of.items():
                for sid in sources:
                    rev_fields[tgt] |= src_fields.get(sid, set())

        # 5) translations of the adjectives themselves — all, order as stored
        tr_of = defaultdict(list)
        for aid, rus in ArticleIndexTranslate.objects.filter(
            article_id__in=adj_ids
        ).values_list("article_id", "rus_word"):
            if rus:
                tr_of[aid].append(rus)

        # 6) assemble: field_name -> {display_word: ref_note}
        # display line = "слово: перевод, перевод"; the "(см. донор)" note is
        # appended after the translations at emit time.
        # «см.» is driven purely by the link (donor_of): it is shown whenever the
        # article points somewhere and the donor prints a DIFFERENT word — even if
        # the article has its own semantic fields. Fields for placement: the
        # article's own if it has any, otherwise the donor's (transitive); if
        # neither — «Без поля». Translations: own if any, otherwise the donor's.
        by_field = defaultdict(dict)
        no_field = {}
        for aid in adj_ids:
            art = articles.get(aid)
            if art is None:
                continue
            nw = self._norm(art)
            did = donor_of.get(aid)

            # translations: only the article's own — never borrow the donor's
            trs = list(tr_of.get(aid, []))
            disp = f"{nw}: {', '.join(trs)}" if trs else nw

            # «см. донор» — whenever a link exists and the donor prints differently
            note = ""
            if did:
                dw = donor_word.get(did, "")
                if dw and dw != nw:
                    note = f" (см. {dw})"

            # placement: own fields → donor's (outgoing «см.») → inherited from
            # incomers (reverse) → «Без поля»
            fields = (
                own.get(aid)
                or (donor_fields.get(did) if did else None)
                or rev_fields.get(aid)
            )
            if fields:
                for fname in fields:
                    by_field[fname].setdefault(disp, note)
            else:
                no_field.setdefault(disp, note)

        # 7) emit markdown in SemanticField.sorting order
        lines = []
        n_words = 0
        fields_used = 0
        for sf in SemanticField.objects.all().order_by("sorting", "name"):
            words = by_field.get(sf.name)
            if not words:
                continue
            fields_used += 1
            lines.append(f"### {sf.name}")
            if sf.definition:
                lines.append(sf.definition)
            lines.append("")
            for w in sorted(words, key=self._sort_key):
                lines.append(f"- {w}{words[w]}")
                n_words += 1
            lines.append("")

        if no_field:
            lines.append("### Без поля")
            lines.append(
                "Прилагательные-отсылки без распределённого донора и прочие "
                "нераспределённые формы."
            )
            lines.append("")
            for w in sorted(no_field, key=self._sort_key):
                lines.append(f"- {w}{no_field[w]}")
                n_words += 1
            lines.append("")

        text = "\n".join(lines).rstrip() + "\n"
        with open(opts["out"], "w", encoding="utf-8") as f:
            f.write(text)

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: {opts['out']}. Полей с прилагательными: {fields_used}, "
                f"строк-слов: {n_words}, без поля: {len(no_field)}."
            )
        )
        if self._norm_errors:
            self.stdout.write(
                self.style.WARNING(
                    f"Заголовков, где normalization() упала (выведено сырьё): "
                    f"{self._norm_errors}."
                )
            )
