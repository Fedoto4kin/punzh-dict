import re

# Shared with lexical /search/, AI axes, translation index, offline cleanup.
_YO_TO_E = str.maketrans({"ё": "е", "Ё": "Е"})
# Russian public search / debug: ё→е plus form wildcards (? any sequence, . one char).
_RUS_QUERY_TRANS = str.maketrans({"ё": "е", "Ё": "Е", "?": "%", ".": "_"})

# Caps ILIKE/token cost; same bound for lexical views and AI job/parse.
MAX_SEARCH_QUERY_LEN = 300


def normalize_yo(text):
    """Map ё/Ё → е/Е. Empty/None → empty string."""
    return (text or "").translate(_YO_TO_E)


def prepare_rus_query(text):
    """
    Prep a Russian search string for ILIKE / token-OR (views + search_debug).
    Strip edges, ё→е, map ?→% and .→_.
    """
    return (text or "").strip().translate(_RUS_QUERY_TRANS)


def canonical_rus_word(text):
    """
    Canonical rus_word for ArticleIndexTranslate storage and dedupe keys.
    Collapses whitespace; maps ё/Ё → е/Е.
    """
    if not text:
        return ""
    return normalize_yo(re.sub(r"\s+", " ", str(text).strip()))


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
