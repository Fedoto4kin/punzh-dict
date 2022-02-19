import re


def normalization(header):

    word = header
    var = None
    appendix = None

    if ',' in header:
        if '~' in header:
            appendix = re.search(r'~(.*)', header).group(1)
        else:
            var = re.search(r',\s(.*)', header).group(1)
        word = header.split(',')[0]

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
        return re.sub(r'([dlnrszt])(\w)’', r'\1’\2’', word)

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
