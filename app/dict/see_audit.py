"""Классификация отсылок «см./ср.» и дериваций «от» в article_html."""

import re

KARELIAN = r"[A-Za-z’ÜüÄäÖöŠšČčŽži̮]+"

# как make_link: канон только кириллица + точка внутри <i>
CANON = re.compile(rf"<i>(см\.|ср\.)</i>\s+({KARELIAN});?")
ITALIC = re.compile(r"<i>([^<]*)</i>", re.IGNORECASE)
# после канона — ещё леммы через запятую
COMMA_TAIL = re.compile(rf"\s*,\s*({KARELIAN})")
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
        extra = COMMA_TAIL.match(tail)
        lemmas = [lemma]
        while extra:
            lemmas.append(extra.group(1))
            out["lemmas"].append((extra.group(1), "comma"))
            tail = tail[extra.end() :]
            extra = COMMA_TAIL.match(tail)
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
