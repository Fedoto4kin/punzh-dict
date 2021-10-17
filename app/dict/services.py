import re


def sorted_by_krl(article, field='first_trigram'):

    return [
        article.get_krl_abc().index(c)
        for c in ''.join(
            [c for c in getattr(article, field).replace('i̮a', 'ua') if c in set(article.get_krl_abc())]
        )
    ]


def gen_word_variants(word) -> ():

    def proc(w, word):

        variants = []
        w = w.strip()

        if w.count('~'):
            # TODO: comment for regexp
            base = re.search(r'[^,|]*', word).group()
            w = w.replace('~', base)

        if w.count('w'):

            for part in re.findall('(?:\w+w[^|]*)', w):
                if not any(el in part for el in ['a', 'o', 'u']):
                    variants.append(
                        w.replace(part, part.replace('w', 'ü'))
                    )
                else:
                    variants.append(
                        w.replace(part, part.replace('w', 'u'))
                    )

            variants.append(w.replace('w', 'v'))

        if w.count('ü'):
            variants.append(w.replace('ü', 'y'))

        if w.count('i̮a'):
            variants.append(w.replace('i̮a', 'ia'))

        _ = re.search(r'\(.*\)', word)
        if _:
            variants.append(w.replace(_.group(), ''))
            w = w.replace('(', '').replace(')', '')

        variants.append(w)
        return variants

    variants = []
    word = re.sub('(I+)$', '', word)
    word = word.replace('˛', '')

    for w in word.split(','):
        variants += proc(w, word)

        # TODO: comment for regexp
        if w.count('|') \
                and not re.findall(r'([|])\1{1,2}', w):
            for _ in w.split('|'):
                variants += proc(_, word)

    no = []
    for v in variants:
        no.append(new_orthography(v))
    variants += no

    return set([
        i.strip().replace('’', '')
            .replace('||', '')
            .replace('|', '')
        for i in variants
    ])

def normalization(header):

    word = header
    var = None
    appendix = None

    if ',' in header:
        if '~' in header:
            appendix = re.search(r'~(.*)', header).group(1)
        else:
            var = re.search(r',\s(.*)', header).group(1)
        word = re.search(r'(.*),', header).group(1)

    base = re.split(r'\|{2}', word)[0]
    word = word.replace('||', '')
    res = new_orthography(word)

    if appendix:
        var = base + appendix

    if var:
        res += ', ' + new_orthography(var)

    return res


def new_orthography(word):

    w = []

    def clear_pallat(word):
        word = re.sub(r'(’)([^aou$])', r'\2', word)
        return re.sub(r'([^aeioui̮äöü])(\w)’', r'\1’\2’', word)

    def part_proc(word):

        word = word.replace('ü', 'y').replace('Ü', 'Y')
        if word.count('w'):
            for part in re.findall('(?:\w+w[^|]*)', word):
                if not any(el in part for el in ['a', 'o', 'u']):
                    word = word.replace(part, part.replace('w', 'y'))
                else:
                    word = word.replace(part, part.replace('w', 'u'))

        return word

    if word.count('|'):
        for _ in word.split('|'):
            w.append(part_proc(_))
    else:
        w.append(part_proc(word))

    return clear_pallat(''.join(w))



