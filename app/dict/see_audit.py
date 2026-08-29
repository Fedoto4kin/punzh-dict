"""Классификация отсылок «см./ср.» и дериваций «от» в article_html."""

import re

# Одно «слово» заголовка (в т.ч. с дефисом). Пробельные двухсловные леммы —
# отдельно: KARELIAN = слово + опциональные продолжения.
KARELIAN_WORD = r"[A-Za-z’'ÜüÄäÖöŠšČčŽži̮\-]+"
# омоним после леммы: «mado 2», «šano I», «kappa I 2» — не часть ссылки
# римский номер только UPPERCASE (I, II): строчная «i»/«v» — союз или начало иллюстрации
# («см. X; har’jatešša i kuduos…»), не омоним
_ROMAN = rf"[IVX]{{1,5}}(?!{KARELIAN_WORD})"
# продолжение леммы через пробел: не омонимный номер (I / 2) и не начало списка
_KRL_CONT = rf"(?!(?:[IVX]{{1,5}}|\d+)(?!{KARELIAN_WORD})){KARELIAN_WORD}"
KARELIAN = rf"{KARELIAN_WORD}(?:\s+{_KRL_CONT})*"
HOMONYM = rf"(?:\s+(?:\d+|{_ROMAN}))*"
HOMONYM_REQ = rf"(?:\s+(?:\d+|{_ROMAN}))+"
COMMA_SEP = r"\s*,\s*"
# хвост омонима у заголовка: «čašk||a I», «bul’u II»
_HOMONYM_TAIL = re.compile(r"(?:\s+(?:\d+|[IVXivx]{1,5}))+$")

# как make_link: канон только кириллица + точка внутри <i>
CANON = re.compile(rf"<i>(см\.|ср\.)</i>\s+({KARELIAN}){HOMONYM}")
ITALIC = re.compile(r"<i>([^<]*)</i>", re.IGNORECASE)
# запятая — следующий элемент списка; «;» — только если у следующей леммы
# есть номер омонима (иначе конец отсылки и иллюстрация: «см. X; istuw…»)
COMMA_MORE = re.compile(rf"{COMMA_SEP}({KARELIAN}){HOMONYM}")
SEMI_MORE = re.compile(rf"\s*;\s*({KARELIAN}){HOMONYM_REQ}")
DERIV_TAGGED = re.compile(
    rf"<i>\s*(freq|caus|mom|refl)\s*</i>\s+от\s+({KARELIAN})",
    re.IGNORECASE,
)
DERIV_LOOSE = re.compile(rf"(?:^|[\s>])от\s+({KARELIAN})")

# визуальные двойники с/м/р в маркере
_FOLD = str.maketrans(
    {
        "c": "с",
        "C": "с",
        "m": "м",
        "M": "м",
        "p": "р",
        "P": "р",
        "r": "р",
        "R": "р",
    }
)


def _fold_marker(text):
    compact = re.sub(r"\s+", "", text.strip()).translate(_FOLD).lower()
    return compact


def is_see_marker(inner):
    """True, если содержимое <i> — это см/ср (в т.ч. кривое)."""
    folded = _fold_marker(inner)
    return folded in {"см", "см.", "ср", "ср."}


def marker_issues(inner):
    """Проблемы канона для содержимого <i>. Пусто — канон см./ср."""
    issues = []
    raw = inner.strip()
    if raw in ("см.", "ср."):
        return issues
    folded = _fold_marker(inner)
    if folded not in {"см", "см.", "ср", "ср."}:
        return issues
    if any(ch in raw for ch in "cCmMpPrR"):
        issues.append("mixed_script")
    if not raw.endswith("."):
        issues.append("no_period")
    if raw != raw.strip() or " " in inner.strip():
        issues.append("spaced")
    if not issues:
        # прочий мусор вокруг канона (см. также и т.п. сюда не попадает)
        issues.append("other_marker")
    return issues


def _strip_italics(html):
    return ITALIC.sub(" ", html)


def classify_html(html):
    """
    Разбор одного html. Ключи — списки совпадений (dict).
    """
    html = html or ""
    out = {
        "canon": [],
        "no_period": [],
        "mixed_script": [],
        "spaced": [],
        "other_marker": [],
        "bare": [],
        "comma_list": [],
        "deriv_tagged": [],
        "deriv_loose": [],
        "lemmas": [],  # (lemma, source) для резолва
    }

    for m in CANON.finditer(html):
        lemma = m.group(2)
        out["canon"].append({"marker": m.group(1), "lemma": lemma, "span": m.group(0)})
        out["lemmas"].append((lemma, "canon"))
        tail = html[m.end() :]
        lemmas = [lemma]
        while True:
            extra = COMMA_MORE.match(tail) or SEMI_MORE.match(tail)
            if not extra:
                break
            lemmas.append(extra.group(1))
            out["lemmas"].append((extra.group(1), "comma"))
            tail = tail[extra.end() :]
        if len(lemmas) > 1:
            out["comma_list"].append({"lemmas": lemmas, "span": m.group(0)})

    for m in ITALIC.finditer(html):
        inner = m.group(1)
        for issue in marker_issues(inner):
            out[issue].append({"inner": inner, "span": m.group(0)})

    stripped = _strip_italics(html)
    bare_re = re.compile(
        rf"(?<!\d)(?<![А-Яа-яЁё])([cсCС][mмMМ]|[cсCС][pрPР])\.?\s+({KARELIAN})"
    )
    for m in bare_re.finditer(stripped):
        marker, lemma = m.group(1), m.group(2)
        out["bare"].append({"marker": marker, "lemma": lemma, "span": m.group(0)})
        out["lemmas"].append((lemma, "bare"))
        if any(ch in marker for ch in "cCmMpP"):
            out["mixed_script"].append({"inner": marker, "span": m.group(0)})

    tagged_spans = []
    for m in DERIV_TAGGED.finditer(html):
        rec = {"tag": m.group(1), "lemma": m.group(2), "span": m.group(0)}
        out["deriv_tagged"].append(rec)
        out["lemmas"].append((m.group(2), "deriv"))
        tagged_spans.append((m.start(), m.end()))

    def in_tagged(pos):
        return any(a <= pos < b for a, b in tagged_spans)

    for m in DERIV_LOOSE.finditer(html):
        if in_tagged(m.start()):
            continue
        out["deriv_loose"].append({"lemma": m.group(1), "span": m.group(0)})
        out["lemmas"].append((m.group(1), "deriv_loose"))

    return out


SEE_LEMMA_SOURCES = frozenset({"canon", "comma", "bare"})


def html_see_lemmas(html):
    """Леммы после см./ср. (без дериваций «от»)."""
    return [
        lemma
        for lemma, src in classify_html(html)["lemmas"]
        if src in SEE_LEMMA_SOURCES
    ]


def fold_lemma(word):
    """
    Свернуть лемму/заголовок для сверки: без ||/|, апострофов, номера омонима,
    хвоста после запятой; š/č/ž → s/c/z (как в ArticleIndexWord).
    """
    if not word:
        return ""
    w = word.lower().replace("||", "").replace("|", "")
    for ch in "’'`ʼʹ":
        w = w.replace(ch, "")
    w = w.split(",", 1)[0].strip()
    w = _HOMONYM_TAIL.sub("", w).strip()
    w = w.replace("~", "")
    # дефис внутри леммы ≈ пробел (mul’l’in-mal’l’in ↔ mul’l’in mal’l’in)
    w = re.sub(r"(?<=\w)-(?=\w)", " ", w)
    return w.replace("š", "s").replace("č", "c").replace("ž", "z")


def html_see_mentions(html, target_words):
    """Есть ли в html отсылка см./ср. на одно из слов цели."""
    lemmas = {fold_lemma(lemma) for lemma in html_see_lemmas(html)} - {""}
    targets = {fold_lemma(w) for w in target_words if w} - {""}
    return bool(lemmas & targets)


CROOKED_KEYS = ("no_period", "mixed_script", "spaced", "bare")


def is_crooked(html):
    c = classify_html(html)
    return any(c[k] for k in CROOKED_KEYS)


def _canonical_mark(raw):
    folded = _fold_marker(raw).rstrip(".")
    if folded == "ср":
        return "ср."
    if folded == "см":
        return "см."
    return None


# <i>см</i>. / <i>сp.</i> / <i>ср</i>
ITALIC_CROOKED = re.compile(
    r"<i>\s*([cсCС][mмMМpрPРrR]\.?)\s*</i>\.?",
)
BARE_SEE = re.compile(
    rf"(?<!\d)(?<![А-Яа-яЁё])([cсCС][mмMМ]|[cсCС][pрPР])\.?\s+({KARELIAN})"
)


def propose_html_fix(html):
    """Канонизировать маркеры см./ср. Повторно безопасна (идемпотентна)."""
    html = html or ""

    def repl_italic(m):
        mark = _canonical_mark(m.group(1))
        if mark is None:
            return m.group(0)
        return f"<i>{mark}</i>"

    html = ITALIC_CROOKED.sub(repl_italic, html)

    def repl_bare(m):
        mark = _canonical_mark(m.group(1))
        if mark is None:
            return m.group(0)
        return f"<i>{mark}</i> {m.group(2)}"

    return BARE_SEE.sub(repl_bare, html)


# опциональное окончание в скобках только для подсветки: kurpa(t) → /search/kurpat
_OPT_PAREN = r"(?:\([^)]*\))?"
SEE_ITEM = rf"{KARELIAN}{_OPT_PAREN}{HOMONYM}"
SEE_AFTER_SEMI = rf"{KARELIAN}{_OPT_PAREN}{HOMONYM_REQ}"
SEE_LIST = re.compile(
    rf"<i>(см\.|ср\.)</i>\s+("
    rf"{SEE_ITEM}(?:{COMMA_SEP}{SEE_ITEM}|\s*;\s*{SEE_AFTER_SEMI})*"
    rf")(\s*[;,]?)?"
)
_SEE_TOKEN = re.compile(
    "("
    + KARELIAN
    + r")(\([^)]*\))?((?:\s+(?:\d+|"
    + _ROMAN
    + r"))*)|("
    + COMMA_SEP
    + r"|\s*;\s*)"
)


def link_see_lemmas(html):
    """
    Обернуть каждое слово после «см./ср.»; номера омонимов не трогать.
    kurpa(t) в тексте — ссылка на /search/kurpat (скобки в href снимаются).
    Двухсловные леммы через пробел (не через запятую) — одна ссылка.
    """
    html = html or ""

    def repl(m):
        mark, blob, tail_sep = m.group(1), m.group(2), m.group(3) or ""
        bits = []
        for token in _SEE_TOKEN.finditer(blob):
            word, paren, hom, sep = (
                token.group(1),
                token.group(2),
                token.group(3),
                token.group(4),
            )
            if word:
                display = word + (paren or "")
                href = display.replace("(", "").replace(")", "").replace(" ", "%20")
                bits.append(f'<a href="/search/{href}">{display}</a>')
                if hom:
                    bits.append(hom)
            else:
                bits.append(sep)
        return f"<i>{mark}</i> {''.join(bits)}{tail_sep}"

    return SEE_LIST.sub(repl, html)


def article_headword_keys(article):
    """
    Формы основного заголовка (до запятой), без нарезки сложений по «|».
    «riw||gu, ~gun’e» → riwgu, riugu, rivgu; «riwgu|meččä» → riwgumeččä…
    """
    from dict.helpers.variants import gen_word_variants

    keys = set()

    def add_glued(raw):
        if not raw:
            return
        glued = raw.replace("||", "").replace("|", "").strip()
        glued = _HOMONYM_TAIL.sub("", glued).strip()
        if not glued:
            return
        keys.add(fold_lemma(glued))
        for v in gen_word_variants(glued):
            folded = fold_lemma(v)
            if folded:
                keys.add(folded)

    add_glued((article.word or "").split(",")[0])
    if getattr(article, "word_normalized", None):
        add_glued(article.word_normalized.split(",")[0])
    return {k for k in keys if k}


def lemma_matches_headword(article, lemma):
    folded = fold_lemma(lemma)
    return bool(folded) and folded in article_headword_keys(article)


def lookup_articles(lemma, exclude_id=None):
    """Статьи по лемме (индекс заголовка, иначе krl ilike)."""
    from dict.models import Article, ArticleIndexWord
    from dict.search import krl_article_ids

    ids = list(
        ArticleIndexWord.objects.filter(word__iexact=lemma)
        .values_list("article_id", flat=True)
        .distinct()
    )
    folded = fold_lemma(lemma)
    if not ids and folded and folded != lemma.lower():
        ids = list(
            ArticleIndexWord.objects.filter(word__iexact=folded)
            .values_list("article_id", flat=True)
            .distinct()
        )
    if not ids:
        ids = list(krl_article_ids(lemma)[:20])
    qs = Article.objects.filter(pk__in=ids)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    found = list(qs.order_by("word"))
    # «см. riwgu» не должно цеплять сложения bad’ja|riwgu, если есть riw||gu
    primary = [a for a in found if lemma_matches_headword(a, lemma)]
    if primary:
        return primary
    return found


def article_index_words(article):
    from dict.models import ArticleIndexWord

    words = {article.word}
    for w in ArticleIndexWord.objects.filter(article=article).values_list(
        "word", flat=True
    ):
        if w:
            words.add(w)
    return words


def lemma_resolves_to(lemma, from_id, to_article):
    """Лемма из HTML указывает на to_article."""
    found = lookup_articles(lemma, from_id)
    if any(a.id == to_article.id for a in found):
        return True
    return lemma_matches_headword(to_article, lemma)


def infer_link_kind(from_article, to_article):
    """
    Угадать kind существующей связи по HTML источника.
    deriv имеет приоритет над см./ср.; иначе дефолт see.
    """
    from dict.models import ArticleLink

    html = from_article.article_html or ""
    from_id = from_article.id
    c = classify_html(html)

    for rec in c["deriv_tagged"]:
        if lemma_resolves_to(rec["lemma"], from_id, to_article):
            return ArticleLink.KIND_DERIV
    for rec in c["deriv_loose"]:
        if lemma_resolves_to(rec["lemma"], from_id, to_article):
            return ArticleLink.KIND_DERIV

    for m in CANON.finditer(html):
        mark = m.group(1)
        cross_kind = (
            ArticleLink.KIND_CF if mark.startswith("ср") else ArticleLink.KIND_SEE
        )
        lemma = m.group(2)
        lemmas = [lemma]
        tail = html[m.end() :]
        while True:
            extra = COMMA_MORE.match(tail) or SEMI_MORE.match(tail)
            if not extra:
                break
            lemmas.append(extra.group(1))
            tail = tail[extra.end() :]
        for lem in lemmas:
            if lemma_resolves_to(lem, from_id, to_article):
                return cross_kind

    return ArticleLink.KIND_SEE


def scan_see_links(article, outgoing):
    """
    Сверка лемм «см./ср.» в HTML с исходящими ArticleLink.
    Деривации «от» не входят. HTML не меняет.
    """
    html = article.article_html or ""
    lemmas = html_see_lemmas(html)
    linked_ids = {lnk.to_article_id for lnk in outgoing}
    unique_missing = []
    unresolved = []
    homonym = []
    for lemma in lemmas:
        found = lookup_articles(lemma, article.id)
        ids = {a.id for a in found}
        if not found:
            unresolved.append({"lemma": lemma, "found": []})
        elif len(found) > 1:
            if not (ids & linked_ids):
                homonym.append({"lemma": lemma, "found": found})
        else:
            tgt = found[0]
            if tgt.id not in linked_ids:
                unique_missing.append({"lemma": lemma, "target": tgt})
    extra = []
    for lnk in outgoing:
        if any(lemma_matches_headword(lnk.to_article, lemma) for lemma in lemmas):
            continue
        if html_see_mentions(html, article_index_words(lnk.to_article)):
            continue
        extra.append(lnk)
    return {
        "unique_missing": unique_missing,
        "unresolved": unresolved,
        "homonym": homonym,
        "extra": extra,
    }


def html_deriv_lemmas(html):
    """Леммы из дериваций «от» (tagged + loose), без дублей."""
    c = classify_html(html or "")
    seen = []
    for rec in c["deriv_tagged"]:
        lemma = rec["lemma"]
        if lemma not in seen:
            seen.append(lemma)
    for rec in c["deriv_loose"]:
        lemma = rec["lemma"]
        if lemma not in seen:
            seen.append(lemma)
    return seen


def scan_deriv_links(article, outgoing):
    """
    Сверка лемм «от» в HTML с исходящими ArticleLink.
    HTML не меняет. См./ср. не входят.
    """
    from dict.models import ArticleLink

    html = article.article_html or ""
    c = classify_html(html)
    links_by_to = {lnk.to_article_id: lnk for lnk in outgoing}
    linked_ids = set(links_by_to.keys())
    unique_missing = []
    unresolved = []
    homonym = []
    wrong_kind = []
    already = []

    def process(lemma, source):
        found = lookup_articles(lemma, article.id)
        ids = {a.id for a in found}
        row = {"lemma": lemma, "source": source}
        if not found:
            unresolved.append({**row, "found": []})
            return
        if len(found) > 1:
            if ids & linked_ids:
                for a in found:
                    if a.id not in linked_ids:
                        continue
                    lnk = links_by_to[a.id]
                    entry = {**row, "target": a, "link": lnk, "found": found}
                    if lnk.kind == ArticleLink.KIND_DERIV:
                        already.append(entry)
                    else:
                        wrong_kind.append(entry)
                    return
            homonym.append({**row, "found": found})
            return
        tgt = found[0]
        if tgt.id not in linked_ids:
            unique_missing.append({**row, "target": tgt})
            return
        lnk = links_by_to[tgt.id]
        entry = {**row, "target": tgt, "link": lnk}
        if lnk.kind == ArticleLink.KIND_DERIV:
            already.append(entry)
        else:
            wrong_kind.append(entry)

    for rec in c["deriv_tagged"]:
        process(rec["lemma"], "tagged")
    for rec in c["deriv_loose"]:
        process(rec["lemma"], "loose")

    return {
        "unique_missing": unique_missing,
        "unresolved": unresolved,
        "homonym": homonym,
        "wrong_kind": wrong_kind,
        "already": already,
    }
