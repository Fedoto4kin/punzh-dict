import re

# Canonical dictionary apostrophe (RIGHT SINGLE QUOTATION MARK).
KRL_APOSTROPHE = "\u2019"

# All apostrophe / palatalization lookalikes we fold or accept as the same mark.
# Single source of truth — search index, query fold, see-audit, audits, agents.
KRL_APOSTROPHES = frozenset(
    {
        KRL_APOSTROPHE,  # ’ U+2019
        "'",  # ' U+0027 ASCII
        "`",  # ` U+0060 grave
        "\u02BC",  # ʼ modifier letter apostrophe
        "\u02B9",  # ʹ modifier letter prime
        "\u00B4",  # ´ acute accent
    }
)

_STRIP_APOS = str.maketrans({ch: None for ch in KRL_APOSTROPHES})


def krl_apostrophes_class():
    """Characters for embedding inside a [...] regex class."""
    return "".join(KRL_APOSTROPHES)


def strip_krl_apostrophes(text):
    return (text or "").translate(_STRIP_APOS)


def canonicalize_krl_apostrophes(text):
    """Map every lookalike to the dictionary mark U+2019."""
    out = text or ""
    for ch in KRL_APOSTROPHES:
        if ch != KRL_APOSTROPHE:
            out = out.replace(ch, KRL_APOSTROPHE)
    return out


def normalization(header):

    word = header
    var = None
    appendix = None

    if "," in header:
        if "~" in header:
            appendix = re.search(r"~(.*)", header).group(1)
        else:
            var = re.search(r",\s(.*)", header).group(1)
        word = header.split(",")[0]

    base = re.split(r"\|{2}", word)[0]
    word = word.replace("||", "")
    res = new_orthography(word)

    if appendix:
        var = base + appendix
    if var:
        res += ", " + new_orthography(var)

    return res


def new_orthography(word):

    w = []

    def clear_pallat(word):
        word = canonicalize_krl_apostrophes(word)
        word = re.sub(rf"({re.escape(KRL_APOSTROPHE)})([^aou$])", r"\2", word)
        return re.sub(
            rf"([dlnrszt])(\w){re.escape(KRL_APOSTROPHE)}",
            rf"\1{KRL_APOSTROPHE}\2{KRL_APOSTROPHE}",
            word,
        )

    def part_proc(word):

        word = word.replace("ü", "y").replace("Ü", "Y")
        if word.count("w"):
            for part in re.findall(r"(?:\w+w[^|]*)", word):
                if not any(el in part for el in ["a", "o", "u"]):
                    word = word.replace(part, part.replace("w", "y"))
                else:
                    word = word.replace(part, part.replace("w", "u"))

        return word

    if word.count("|"):
        for _ in word.split("|"):
            w.append(part_proc(_))
    else:
        w.append(part_proc(word))

    return clear_pallat("".join(w))
