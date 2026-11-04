"""
Russian query tokenization shared by lexical /search/, AI retrieval, and audits.

Public API — do not re-copy token regex / stop lists / boundary patterns.
"""

import re

TOKEN_RE = re.compile(r"[а-яё\-]+", re.IGNORECASE)

# Stop-words for the narrowing split (SPEC v2 §5): corpus buckets 1a (len<=2)
# and 1b (dictionary abbreviations ending in -л). Static list.
STOP_1A = {
    "в",
    "с",
    "на",
    "и",
    "из",
    "по",
    "от",
    "к",
    "со",
    "о",
    "за",
    "до",
    "во",
    "не",
    "у",
    "то",
    "же",
    "ее",
    "ни",
    "да",
    "но",
    "ко",
    "а",
    "бы",
    "ли",
    "их",
    "им",
    "та",
    "вы",
    "об",
    "ле",
    "те",
    "он",
    "мы",
}
STOP_1B = {
    "что-л",
    "чем-л",
    "чего-л",
    "кого-л",
    "чему-л",
    "куда-л",
    "кем-л",
    "где-л",
    "кому-л",
    "какое-л",
    "какого-л",
    "каком-л",
    "откуда-л",
    "каким-л",
    "какую-л",
    "каких-л",
    "какой-л",
    "какие-л",
    "чью-л",
    "чьего-л",
    "какая-л",
}
STOPWORDS = STOP_1A | STOP_1B

# Short-prefix fuzzy token match (backlog P3 surrogate): «корова» → «корове».
FUZZY_TOKEN_MIN_LEN = 5
# One inflection letter (корова/корове); not derivational siblings (понизу/понизить).
_FUZZY_SUFFIX = r"[а-яё]"

# Token boundary for rus_word: same alphabet as TOKEN_RE ([а-яё\-] tokens).
_TOKEN_BOUNDARY_BEFORE = r"(?:^|[^а-яё\-])"
_TOKEN_BOUNDARY_AFTER = r"(?:$|[^а-яё\-])"


def query_tokens(query):
    """Lowercase Cyrillic/hyphen tokens from a Russian query string."""
    return TOKEN_RE.findall((query or "").lower())


def token_boundary_regex(token):
    """Whole-token match of `token` inside rus_word (Postgres iregex)."""
    return _TOKEN_BOUNDARY_BEFORE + re.escape(token) + _TOKEN_BOUNDARY_AFTER


def token_boundary_fuzzy_regex(token):
    """Stem = token minus last letter; matches inflection variants (корова/корове)."""
    stem = token[:-1]
    return (
        _TOKEN_BOUNDARY_BEFORE + re.escape(stem) + _FUZZY_SUFFIX + _TOKEN_BOUNDARY_AFTER
    )
