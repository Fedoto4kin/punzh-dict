import re

# Same as views.search ILIKE prep and translation_cleanup sanitize (ё→е).
_YO_TO_E = str.maketrans({"ё": "е", "Ё": "Е"})


def canonical_rus_word(text):
    """
    Canonical rus_word for ArticleIndexTranslate storage and dedupe keys.
    Collapses whitespace; maps ё/Ё → е/Е.
    """
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text).strip()).translate(_YO_TO_E)


def dedupe_canonical_rus_words(words):
    """Unique non-empty rus_word strings in canonical form (order preserved)."""
    seen = set()
    out = []
    for word in words:
        if not isinstance(word, str):
            continue
        canonical = canonical_rus_word(word)
        if not canonical:
            continue
        key = canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(canonical)
    return out
