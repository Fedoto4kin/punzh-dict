import re

from .orphography import new_orthography, normalization

KRL_ABC = "ABCČDEFGHIJKLMNOPRSŠZŽTUVYÄÖ"


def sorted_by_krl(article, field="first_trigram"):

    def prepare_word(word):
        return normalization(
            re.split(r"\s|,", word.replace("i̮a", "ua"), maxsplit=1)[0]
        ).lower()

    return [
        article.get_krl_abc().index(c)
        for c in "".join(
            [
                c
                for c in prepare_word(getattr(article, field))
                if c in set(article.get_krl_abc())
            ]
        )
    ]


def r_gen_word_variants(word, _word) -> ():

    def r_proc(w, word):
        variants = []
        w = w.strip()

        if w.count("~"):
            # TODO: comment for regexp
            base = re.search(r"[^,|]*", word).group()
            w = w.replace("~", base)

        if w.count("ü"):
            variants.append(w.replace("ü", "y"))

        _ = re.search(r"\(.*\)", word)
        if _:
            variants.append(w.replace(_.group(), ""))
            w = w.replace("(", "").replace(")", "")

        variants.append(w)
        return variants

    def proc(w, word):
        variants = []
        w = w.strip()

        if w.count("uu"):
            variants.append(w.replace("uu", "uw"))
            variants.append(w.replace("uu", "uv"))
        if w.count("yy"):
            variants.append(w.replace("yy", "yw"))
            variants.append(w.replace("yy", "yv"))
        if w.count("eu"):
            variants.append(w.replace("eu", "ew"))
            variants.append(w.replace("eu", "ev"))
        if w.count("ey"):
            variants.append(w.replace("ey", "ew"))
            variants.append(w.replace("ey", "ev"))
        if w.count("au"):
            variants.append(w.replace("au", "aw"))
            variants.append(w.replace("au", "av"))
        if w.count("äy"):
            variants.append(w.replace("äy", "äw"))
            variants.append(w.replace("äy", "äv"))
        if w.count("y"):
            variants.append(w.replace("y", "ü"))

        _ = re.search(r"\(.*\)", word)
        if _:
            variants.append(w.replace(_.group(), ""))
            w = w.replace("(", "").replace(")", "")

        variants.append(w)
        return variants

    variants = []
    word = re.sub("(I+)$", "", word)
    word = word.replace("˛", "")
    word = word.lower()

    for w in word.split(","):
        variants += proc(w, word)
        if w.count("|") and not re.findall(r"([|])\1{1,2}", w):
            for _ in w.split("|"):
                variants += proc(_, word)
    if _word:
        for w in _word.split(","):
            variants += r_proc(w, _word)
            if w.count("|") and not re.findall(r"([|])\1{1,2}", w):
                for _ in w.split("|"):
                    variants += r_proc(_, _word)

    return set(
        [
            i.strip()
            .replace("’", "")
            .replace("||", "")
            .replace("|", "")
            .replace("š", "s")
            .replace("č", "c")
            .replace("ž", "z")
            for i in variants
        ]
    )


def gen_word_variants(word) -> ():

    def proc(w, word):

        variants = []
        w = w.strip()

        if w.count("~"):
            # TODO: comment for regexp
            base = re.search(r"[^,|]*", word).group()
            w = w.replace("~", base)

        if w.count("w"):
            w = w.replace("||", "")
            for part in re.findall("(?:\w+w[^|]*)", w):
                if not any(el in part for el in ["a", "o", "u"]):
                    variants.append(w.replace(part, part.replace("w", "ü")))
                else:
                    variants.append(w.replace(part, part.replace("w", "u")))

            variants.append(w.replace("w", "v"))

        if w.count("ü"):
            variants.append(w.replace("ü", "y"))

        if w.count("i̮a"):
            variants.append(w.replace("i̮a", "ia"))

        _ = re.search(r"\(.*\)", word)
        if _:
            variants.append(w.replace(_.group(), ""))
            w = w.replace("(", "").replace(")", "")

        variants.append(w)
        return variants

    variants = []
    word = re.sub("(I+)$", "", word)
    word = word.replace("˛", "")
    word = word.lower()

    for w in word.split(","):
        variants += proc(w, word)
        if w.count("|") and not re.findall(r"([|])\1{1,2}", w):
            for _ in w.split("|"):
                variants += proc(_, word)

    new_o = []
    for v in variants:
        new_o.append(new_orthography(v))
    variants += new_o

    return set(
        [
            i.strip()
            .replace("’", "")
            .replace("||", "")
            .replace("|", "")
            .replace("š", "s")
            .replace("č", "c")
            .replace("ž", "z")
            for i in variants
        ]
    )


def create_ngram(word, n):

    word = normalization(word.lower().replace("’", ""))
    word = re.split(r"\s|,", word, maxsplit=1)
    return word[0][:n]

def build_pagination_hints(articles, per_page):
    """
    Build the " ·· " navigation hints shown between paginated pages.

    For each page boundary take the first word of the page and find the
    shortest n-gram prefix (n >= 3) that is unambiguous against the first
    words of the neighbouring pages. Each hint is then joined with the
    next one via " ·· ". Returns {page_number: hint}, or {} when empty.
    """
    page_first_words = articles[0::per_page]
    if not page_first_words:
        return {}

    hints = [create_ngram(a.word, 3) for a in page_first_words]

    # Disambiguate each inner boundary against its two neighbours
    for idx in range(1, len(page_first_words) - 1):
        n = 3
        while n <= len(page_first_words[idx].word):
            current = create_ngram(page_first_words[idx].word, n)
            prev_ng = create_ngram(page_first_words[idx - 1].word, n)
            next_ng = create_ngram(page_first_words[idx + 1].word, n)
            hints[idx] = current
            if current[:n] != prev_ng and current[:n] != next_ng:
                break
            n += 1

    # Join each hint with the next page's hint (last one keeps no suffix)
    for idx in range(len(hints) - 1):
        hints[idx] = hints[idx] + " ·· " + hints[idx + 1]

    return dict(zip(range(1, len(hints) + 1), hints))