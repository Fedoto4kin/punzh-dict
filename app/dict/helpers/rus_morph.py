"""
Russian lemmatization for lexical /search/ (P3).

Uses pymorphy3; normal forms are canonicalized with ё→е to match rus_word.
"""

from .rus_tokens import query_tokens
from .rus_word import normalize_yo

_morph = None


def get_morph():
    """Lazy singleton — MorphAnalyzer loads a large dictionary once per process."""
    global _morph
    if _morph is None:
        import pymorphy3

        _morph = pymorphy3.MorphAnalyzer()
    return _morph


def lemma_token(tok):
    """
    Normal form of one Cyrillic token (ё→е). Empty/blank → "".
    Homonymy: top parse only (v1).
    """
    raw = (tok or "").strip().lower()
    if not raw:
        return ""
    parses = get_morph().parse(raw)
    if not parses:
        return normalize_yo(raw)
    return normalize_yo(parses[0].normal_form)


def lemmas_of_phrase(text):
    """
    Unique lemmas of TOKEN_RE tokens in `text`, order of first occurrence.
    Suitable for ArticleIndexTranslate.rus_lemmas.
    """
    seen = []
    for tok in query_tokens(text):
        lem = lemma_token(tok)
        if lem and lem not in seen:
            seen.append(lem)
    return seen


def query_lemmas(query):
    """Lemmas of a search query string (same tokenization as query_tokens)."""
    return lemmas_of_phrase(query)
