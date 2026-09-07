"""Detect Cyrillic leaked into Karelian Latin text. Report-only helpers."""

import re
import unicodedata
from collections import Counter

from dict.models import Article

# Visual lookalikes → Latin. import.py cleaned only а е о с р on headwords.
HOMOGLYPHS = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "і": "i",
        "ӓ": "ä",
        "ӧ": "ö",
        "ү": "y",
        "к": "k",
        "А": "A",
        "Е": "E",
        "О": "O",
        "Р": "P",
        "С": "C",
        "У": "Y",
        "Х": "X",
        "І": "I",
        "Ӓ": "Ä",
        "Ӧ": "Ö",
        "Ү": "Y",
        "К": "K",
        "М": "M",
        "Т": "T",
        "В": "B",
        "Н": "H",
    }
)

# Reverse: Latin lookalikes leaked into Russian glosses (мoлoдoй → молодой).
LATIN_TO_CYR = str.maketrans(
    {
        "a": "а",
        "A": "А",
        "e": "е",
        "E": "Е",
        "o": "о",
        "O": "О",
        "p": "р",
        "P": "Р",
        "c": "с",
        "C": "С",
        "y": "у",
        "Y": "У",
        "x": "х",
        "X": "Х",
    }
)

# Keep | inside compounds; ’ is the dictionary apostrophe. Tilde is not a
# word char: ``~аlla`` is handled by after_tilde + mixed on ``аlla``.
_WORD_EXTRA = set("’'`´|")

_TAG_RE = re.compile(r"<[^>]+>")


def cyrillic_chars(text):
    """Cyrillic letters in *text*, in order of appearance (duplicates kept)."""
    if not text:
        return []
    return [ch for ch in text if "CYRILLIC" in unicodedata.name(ch, "")]


def describe_char(ch):
    return f"{ch} U+{ord(ch):04X} {unicodedata.name(ch, '?')}"


def suggest_latin(text):
    return (text or "").translate(HOMOGLYPHS)


def suggest_cyrillic(text):
    """Map Latin lookalikes to Cyrillic (Russian gloss with OCR Latin leaks)."""
    return (text or "").translate(LATIN_TO_CYR)


def letter_script(ch):
    """'cyr', 'lat', or None for non-letters / other scripts."""
    name = unicodedata.name(ch, "")
    if "CYRILLIC" in name:
        return "cyr"
    if "LATIN" in name:
        return "lat"
    return None


def latin_leak_chars(text):
    """Latin letters that LATIN_TO_CYR would rewrite."""
    if not text:
        return []
    mapped = set()
    for key in LATIN_TO_CYR:
        if isinstance(key, int):
            mapped.add(chr(key))
        else:
            mapped.add(key)
    return [ch for ch in text if ch in mapped]


def is_word_char(ch):
    if ch in _WORD_EXTRA:
        return True
    cat = unicodedata.category(ch)
    # Mn/Mc: i̮ and similar Karelian diacritics.
    return cat.startswith("L") or cat in ("Mn", "Mc")


def strip_html_tags(html):
    return _TAG_RE.sub(" ", html or "")


def _token_scripts(token):
    return {letter_script(ch) for ch in token} - {None}


def _script_counts(token):
    lat = cyr = 0
    for ch in token:
        s = letter_script(ch)
        if s == "lat":
            lat += 1
        elif s == "cyr":
            cyr += 1
    return lat, cyr


def pick_suggestion(value, cyr_letters):
    """
    Choose fix direction and suggested spelling.

    - krl: Cyrillic lookalikes inside Karelian → suggest_latin
    - rus: Latin lookalikes inside Russian → suggest_cyrillic
    """
    to_lat = suggest_latin(value)
    to_cyr = suggest_cyrillic(value)
    if is_homoglyph_only(cyr_letters):
        return "krl", to_lat
    # Mapping Latin→Cyrillic clears all Latin letters → Russian gloss.
    if to_cyr != value and not any(letter_script(ch) == "lat" for ch in to_cyr):
        return "rus", to_cyr
    lat_n, cyr_n = _script_counts(value)
    if cyr_n >= lat_n and to_cyr != value:
        return "rus", to_cyr
    return "krl", to_lat


def _hit(article_id, kind, token, start, display=None):
    value = display if display is not None else token
    bad = cyrillic_chars(token)
    direction, suggested = pick_suggestion(value, bad)
    if direction == "rus":
        leak = latin_leak_chars(value)
        chars = "; ".join(describe_char(ch) for ch in leak) or "(нет лат. омоглифов)"
    else:
        chars = "; ".join(describe_char(ch) for ch in bad)
    return {
        "article_id": article_id,
        "kind": kind,
        "value": value,
        "offset": start,
        "chars": chars,
        "suggested": suggested,
        "cyr_letters": bad,
        "homoglyph_only": is_homoglyph_only(bad),
        "direction": direction,
    }


def homoglyph_char_set():
    """Cyrillic code points present in HOMOGLYPHS (maketrans uses ordinals)."""
    out = set()
    for key in HOMOGLYPHS:
        if isinstance(key, int):
            out.add(chr(key))
        else:
            out.add(key)
    return out


def is_homoglyph_only(cyr_letters):
    """True if every Cyrillic letter is a mapped lookalike (safe auto-suggest)."""
    if not cyr_letters:
        return False
    homo = homoglyph_char_set()
    return all(ch in homo for ch in cyr_letters)


def apply_token_fix(html, value, suggested):
    """
    Replace the first occurrence of *value* in *html* with *suggested*.
    Returns new html, or None if *value* is missing / unchanged.
    """
    html = html or ""
    if not value or value == suggested or value not in html:
        return None
    return html.replace(value, suggested, 1)


def find_html_cyrillic_leaks(html, article_id=None):
    """
    Cyrillic inside Karelian spans of article_html.

    - after_tilde: letters glued to ``~`` (no space) — must be Latin only;
      ``~ мёд`` (space after tilde) is a Russian gloss and is ignored.
    - mixed: one token with both Latin and Cyrillic letters (incl. mid-word).
    """
    text = strip_html_tags(html)
    hits = []
    seen = set()  # (kind, start, value)

    def add(kind, token, start, display=None):
        value = display if display is not None else token
        key = (kind, start, value)
        if key in seen:
            return
        seen.add(key)
        hits.append(_hit(article_id, kind, token, start, display=display))

    # 1) ~continuation — any Cyrillic is wrong (even all-Cyrillic homoglyphs).
    tilde_cont_spans = set()  # (start, end) of continuation after ~
    i = 0
    while True:
        j = text.find("~", i)
        if j < 0:
            break
        k = j + 1
        while k < len(text) and is_word_char(text[k]):
            k += 1
        if k > j + 1:
            cont = text[j + 1 : k]
            if cyrillic_chars(cont):
                tilde_cont_spans.add((j + 1, k))
                add("after_tilde", cont, j, display="~" + cont)
        i = j + 1

    # 2) Mixed-script tokens (Latin + Cyrillic in the same word).
    # Skip spans already reported as after_tilde (same continuation).
    n = len(text)
    pos = 0
    while pos < n:
        if not is_word_char(text[pos]):
            pos += 1
            continue
        start = pos
        while pos < n and is_word_char(text[pos]):
            pos += 1
        if (start, pos) in tilde_cont_spans:
            continue
        token = text[start:pos]
        scripts = _token_scripts(token)
        if scripts >= {"lat", "cyr"}:
            add("mixed", token, start)

    return hits


def scan_cyrillic_in_html():
    """
    Scan all Article.article_html.
    Returns (rows, letter Counter); each row includes word and homoglyph_only.
    """
    rows = []
    letters = Counter()
    qs = Article.objects.values_list("id", "word", "article_html").iterator(
        chunk_size=500
    )
    for pk, word, html in qs:
        for hit in find_html_cyrillic_leaks(html, article_id=pk):
            hit["word"] = word
            hit["article_html"] = html or ""
            rows.append(hit)
            letters.update(hit["cyr_letters"])
    return rows, letters
