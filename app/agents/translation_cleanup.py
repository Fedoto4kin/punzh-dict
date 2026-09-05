"""
Frozen prompt and article input for LLM cleanup of ArticleIndexTranslate.

Offline-only: used by agents/clean_translations.py (and tests). Not imported
from dict/ai/ or runtime code.

See backlog.md §2, agents/AGENTS.md.
"""

import json
import re

from dict.models import ArticleIndexTranslate, Tag

TAG_RE = re.compile(r"<[^>]+>")
# Karelian/Latin tokens (extended Latin + typographic apostrophe U+2019).
_KRL_LETTER = r"A-Za-z\u00C0-\u024F"
_KRL_APOS = r"'\u2019\u02BC"
_LATIN_WORD_RE = re.compile(rf"[{_KRL_LETTER}][{_KRL_LETTER}{_KRL_APOS}\-]*")
# Headword inflection glued to tilde: «~an'e ухо» / «~än’e» (U+2019).
# Not «~ keldan'e жёлтая краска» (space after ~ → Karelian example word).
# Outside [], {_KRL_APOS} would mean three chars in a row — use a character class.
_HEADWORD_SLOT_RE = re.compile(
    rf"^~[{_KRL_LETTER}{_KRL_APOS}\-]*[{_KRL_APOS}][{_KRL_LETTER}{_KRL_APOS}\-]*\s+[а-яё]",
    re.I,
)

# Match build_ontology.py — function-word POS tags.
SERVICE_POS_KEYWORDS = ["союз", "частица", "предлог", "послелог", "междомети"]

_CROSSREF_TOKENS = frozenset({"см", "ср"})

# Single-token auxiliaries dropped when a longer phrase in the list contains them.
_SUBSUMED_AUX_TOKENS = frozenset(
    {
        "быть",
        "был",
        "была",
        "были",
        "есть",
        "будет",
        "становиться",
        "стать",
        "стал",
        "стала",
        "стали",
        "вызывать",
        "оказаться",
        "оказались",
        "являться",
        "иметься",
    }
)

_GRAMMAR_PAREN_HINTS = (
    "функци",
    "связк",
    "вспомогательн",
    "перфект",
    "плюсквамперфект",
    "образован",
    "модальн",
    "безличн",
    "impersonale",
    "глагола-связ",
    # Usage / paradigm notes that often embed Karelian forms (l’ienöw, …).
    "будущ",
    "употребляет",
    "ед.ч",
    "мн.ч",
    "кратк",
    "3л",
)

_PAREN_RE = re.compile(r"\(([^)]*)\)")

# Scope notes in gloss: (о каком-л. действии) — not a distinct index sense.
_SCOPE_PAREN_RE = re.compile(
    r"\s*\((?:о|об|про)\s+каком(?:-л)?\.?[^)]*\)\s*",
    re.I,
)

_YO_TO_E = str.maketrans({"ё": "е", "Ё": "Е"})

# Expanded Latin POS lemmas that appear in gloss HTML / names (not only Tag.tag).
_LATIN_POS_PREFIX_ALTS = (
    r"conj(?:uctio)?|particl(?:a)?|interj(?:ectio)?|verbum|adverbium|"
    r"adjectivum|reflexivum|impersonale"
)

# Tag.type: 3 = stylistic, 4 = dialect (same as query_prompts / views filters).
_DICT_LABEL_TAG_TYPES = (3, 4)

# Optional override for SimpleTestCase (no DB); None → load from Tag.
_forced_dict_label_tokens = None
_label_prefix_re_cache = None
_gloss_label_words_cache = None


def set_dict_label_tokens_for_tests(tokens):
    """
    Pin stylistic/dialect label tokens for tests without DB.
    Pass None to restore DB-backed loading.
    """
    global _forced_dict_label_tokens, _label_prefix_re_cache, _gloss_label_words_cache
    _forced_dict_label_tokens = None if tokens is None else list(tokens)
    _label_prefix_re_cache = None
    _gloss_label_words_cache = None


def clear_dict_label_prefix_cache():
    """Drop compiled prefix regex (call after Tag fixtures change)."""
    global _label_prefix_re_cache, _gloss_label_words_cache
    _label_prefix_re_cache = None
    _gloss_label_words_cache = None


def _normalize_dict_label_token(tag):
    """«всг.» / «перен.» / «с.-х.» → token without a trailing period only."""
    t = (tag or "").strip().lower()
    if not t:
        return ""
    return t.rstrip(".")


def dict_label_tags_from_db():
    """Tag.tag for stylistic (3) and dialect (4) marks — source of truth."""
    return list(
        Tag.objects.filter(type__in=_DICT_LABEL_TAG_TYPES)
        .order_by("type", "sorting", "tag")
        .values_list("tag", flat=True)
    )


def _dict_label_tokens():
    if _forced_dict_label_tokens is not None:
        raw = _forced_dict_label_tokens
    else:
        raw = dict_label_tags_from_db()
    out = []
    seen = set()
    for tag in raw:
        tok = _normalize_dict_label_token(tag)
        if tok and tok not in seen:
            seen.add(tok)
            out.append(tok)
    # Longest first so «с.-х» wins over a hypothetical shorter prefix.
    out.sort(key=len, reverse=True)
    return out


def _label_prefix_re():
    """Leading POS / dict-label stripper; dict part from Tag types 3+4."""
    global _label_prefix_re_cache
    if _label_prefix_re_cache is not None:
        return _label_prefix_re_cache
    alts = [_LATIN_POS_PREFIX_ALTS]
    tokens = _dict_label_tokens()
    if tokens:
        alts.append("|".join(re.escape(t) for t in tokens))
    _label_prefix_re_cache = re.compile(
        r"^(?:" + "|".join(alts) + r")\.?\s+",
        re.I,
    )
    return _label_prefix_re_cache


def _gloss_label_word_set():
    """Single-token label heads used when classifying illustration segments."""
    global _gloss_label_words_cache
    if _gloss_label_words_cache is not None:
        return _gloss_label_words_cache
    words = {
        "impersonale",
        "impers",
        "reflex",
        "reflexivum",
        "conj",
        "particl",
        "interj",
        "verbum",
        "adverbium",
        "adjectivum",
    }
    words.update(_dict_label_tokens())
    _gloss_label_words_cache = frozenset(words)
    return _gloss_label_words_cache


SYSTEM_PROMPT_CLEAN_TRANSLATIONS = (
    "Ты приводишь в порядок РУССКИЕ ПЕРЕВОДЫ одной словарной статьи для "
    "полнотекстового поиска.\n\n"
    "На вход:\n"
    "- translations — текущий список rus_word (может содержать осколки);\n"
    "- gloss_senses — русские gloss'ы по смыслам из статьи (по одному на "
    "<li>, без карельских иллюстраций);\n"
    "- addendum_gloss_senses — то же из аддендумов (может быть пусто);\n"
    "- pos — часть речи леммы (существительное / глагол / прилагательное / …);\n"
    "- pos_tags — полные имена помет; is_service_word;\n"
    "- dict_labels — пометы стиля/говора, их нельзя оставлять в translations.\n\n"
    "Ориентир смыслов — gloss (+ addendum). translations — сырой индекс. "
    "Можно добавлять строки по gloss (параллель, вершина, короткий синоним). "
    "Не выдумывай смыслы вне gloss / translations.\n\n"
    "=== ПРИНЦИПЫ ===\n"
    "1) Вершина по pos: глагол → инфинитив (V); существительное → N/NP; "
    "прилагательное → Adj. Строка индекса = вершина или вершина + зависимые "
    "того же смысла gloss.\n"
    "2) Зависимое без вершины — ошибка (объект, хвост эллипсиса, осколок "
    "параллели). Восстанови «вершина + зависимое».\n"
    "3) Краткий однословный V-вершина параллели обязателен в индексе: "
    "если в gloss краткий инфинитив стоит членом параллели (рядом с другой "
    "полной глагольной фразой и/или перед общим рядом объектов), "
    "он остаётся отдельной строкой. Развёрнутая фраза с тем же V "
    "НЕ заменяет и НЕ отменяет краткую строку. "
    "Если краткий V уже есть в translations — сохрани его.\n"
    "4) Запятая в gloss:\n"
    "   (A) краткий V и полная глагольная фраза как равноправные члены → "
    "обе строки (краткая + полная);\n"
    "   (B) несколько V и общий ряд объектов → размножь каждый V на каждый "
    "полный объект; голый объект без V запрещён; краткие V-вершины "
    "параллели при этом тоже сохраняй (п.3);\n"
    "   • равноправные N/Adj → отдельные строки;\n"
    "   • вершина + причастие / цель / уточнение → одна строка.\n"
    "5) Голый V убирай только если в gloss он не дан отдельным членом "
    "параллели, а встречается лишь внутри более длинной фразы. "
    "Связка: лемма про неё — группы из gloss; иначе не оставляй голую "
    "связку из чужой фразы.\n"
    "6) Форма: сущ./прил. → им. п.; глагол → инфинитив; согласование "
    "внутри фразы едино. Пиши е, не ё (постобработка только ё→е).\n"
    "7) Скобки:\n"
    "   • грам (связка / перфект / модальность) — убери;\n"
    "   • смысловые / scope (о …), (по вкусу) — оставь; общий список "
    "в одних таких скобках — одна строка;\n"
    "   • альтернативные актанты «V (X, Y)» — размножь в «V X», «V Y», "
    "не выпрямляй в «V X, Y»;\n"
    "   • «N (A, B)» с равноправными уточнителями (не о/об/про) → "
    "«N», «N A», «N B».\n"
    "8) Gloss vs иллюстрация: не добавляй смысл, которого нет в gloss, "
    "только из примера. Эквивалент из gloss обязателен, даже если то же "
    "слово есть в иллюстрациях. При «длинный NP, короткий синоним» → "
    "две строки, не кривой эллипсис.\n"
    "9) Без dict_labels и «см./ср. …». Пустой gloss → []. "
    "◊ не добавляй, если нет во входе. "
    "is_service_word: ≤3 слов, без предложений из примеров.\n\n"
    "=== ПРИМЕРЫ ===\n"
    "- (A) «дойти, добраться до какого-л. места; "
    "доходить, доставать до чего-л.» → краткие «дойти», «доходить» "
    "обязательны (+ полные фразы). "
    "Неверно: только «дойти до …» / «доходить до …» без кратких.\n"
    "- (A) «вбирать, впитывать в себя жидкость» → «вбирать» и "
    "«впитывать в себя жидкость» (можно ещё «вбирать в себя жидкость», "
    "но не вместо «вбирать»).\n"
    "- (B) «очищать, разравнивать полосы бересты, лыка, лучины для плетения "
    "лаптей, корзин и пр.» → полные «очищать лучины…», «очищать полосы…», "
    "«разравнивать …» И ОБЯЗАТЕЛЬНО краткие «очищать», «разравнивать». "
    "Неверно: только развёрнутые без «очищать»; неверно: голые "
    "«лучины…», «корзин и пр.».\n"
    "- (B) «вбить, вогнать гвоздь» → «вбить гвоздь», «вогнать гвоздь»; "
    "«гнать смолу, деготь» → «гнать смолу», «гнать деготь» "
    "(не голое «деготь»).\n"
    "- эллипсис: «доходить до ума, до сердца» → «доходить до ума», "
    "«доходить до сердца» (не осколок «до сердца»).\n"
    "- «вызывать отклик» без отдельного «вызывать» в gloss → только фраза.\n"
    "- «вывихивать (руку, ногу)» → «вывихивать руку», «вывихивать ногу».\n"
    "- «нога, опора» + «нога (человека, животного)» → "
    "«нога», «опора», «нога человека», «нога животного».\n"
    "- «охочий, любящий что-л., любящий кого-л.» → отдельные строки.\n"
    "- scope «… (о руке, ноге, языке)» → одна строка со скобками.\n"
    "- «делать более лёгким, менее трудным» → две полные фразы с «делать».\n"
    "- при pos=существительное и именной параллели без V леммы → "
    "полные NP («лучины для плетения лаптей», «лучины для плетения корзин»).\n"
    "- «пиво из сусла второго слива, другач»; в примере «пиво другач» → "
    "«пиво из сусла второго слива» и «другач»; пример НЕ отменяет "
    "короткий эквивалент; не «пиво … второго другач».\n"
    "- причастие/цель → одна строка; согласование: "
    "«соленая голова крупного сома»; без строк с «например»/«напр.»; "
    "не тащи «крепкое пиво» из примера, если gloss только «пиво».\n\n"
    "Отвечай СТРОГО одним JSON без markdown: "
    '{"translations": ["...", ...]}.'
)

SYSTEM_PROMPT_REVIEW_TRANSLATIONS = (
    "Ты — второй проход очистки РУССКОГО поискового индекса словарной статьи.\n"
    "На вход: draft_translations, gloss_senses, addendum_gloss_senses, "
    "pos, pos_tags, is_service_word, dict_labels, "
    "original_translations (сырой индекс до очистки).\n\n"
    "Задача: сверить draft с gloss и исправить ошибки черновика. "
    "Не выдумывай смыслы вне gloss / original. "
    "Если draft верен — верни его же (с ё→е при необходимости).\n\n"
    "=== ПРИНЦИПЫ ===\n"
    "ЧАСТЬ РЕЧИ (pos) задаёт вершину строки: глагол → V; "
    "существительное → N/NP; прилагательное → Adj.\n"
    "1) Строка = вершина ± зависимые того же смысла. "
    "Зависимое без вершины — склей; осколок эллипсиса без вершины — убери. "
    "Краткий равноправный V из gloss — не осколок.\n"
    "2) ОБЯЗАТЕЛЬНАЯ ПРОВЕРКА (глагол): по gloss_senses и "
    "original_translations найди краткие инфинитивы-вершины параллели "
    "(рядом с полной глагольной фразой и/или перед общим рядом объектов). "
    "Каждый такой краткий V должен быть отдельной строкой. "
    "Если draft оставил только развёрнутые «V + объект», а краткого V нет "
    "(хотя он в gloss и/или в original_translations) — ВЕРНИ краткий V. "
    "Развёрнутая строка НЕ заменяет краткую.\n"
    "3) Запятая: (A) краткий V + полная фраза-сосед → обе строки; "
    "(B) несколько V + общий ряд объектов → полные фразы на каждый V "
    "и краткие V-вершины; равноправные N → отдельные строки; "
    "причастие/цель → одна строка.\n"
    "4) Голый V убирай только если в gloss он не дан отдельно. "
    "Не навешивай вершину чужого смысла.\n"
    "5) Скобки: грам — убери; scope (о …) — оставь одной строкой; "
    "«V (X, Y)» → «V X», «V Y»; «N (A, B)» (не о/об/про) → "
    "«N», «N A», «N B».\n"
    "6) Gloss vs иллюстрация: не добавляй только из примера; "
    "эквивалент из gloss обязателен даже при совпадении с иллюстрацией. "
    "«Длинный NP, короткий» → две строки, не кривой эллипсис.\n"
    "7) Убери dict_labels, «см./ср. …», «например». "
    "is_service_word: ≤3 слов. Пиши е, не ё. Пустой gloss → [].\n\n"
    "=== ПРИМЕРЫ ===\n"
    "- (A) draft без «дойти»/«доходить» при gloss "
    "«дойти, добраться…; доходить, доставать…» → ИСПРАВЬ: верни краткие.\n"
    "- (A) draft только «вбирать в себя жидкость», «впитывать…» "
    "без «вбирать» → ИСПРАВЬ: верни «вбирать».\n"
    "- (B) draft только «очищать лучины…» / «очищать полосы…» / "
    "«разравнивать …» без краткого «очищать», а в original было "
    "«очищать» → ИСПРАВЬ: верни «очищать» (и «разравнивать» при нужде).\n"
    "- «доходить до ума, до сердца» → «доходить до ума», "
    "«доходить до сердца» (не осколок «до сердца»).\n"
    "- «вывихивать (руку, ногу)» → «вывихивать руку», «вывихивать ногу».\n"
    "- «нога (человека, животного)» / «нога, опора» → "
    "«нога», «опора», «нога человека», «нога животного».\n"
    "- «гнать смолу, деготь» / «вбить, вогнать гвоздь» → полные фразы.\n"
    "- «пиво из сусла второго слива, другач» (+ пример «пиво другач») → "
    "две строки; короткий «другач» обязателен, пример его не отменяет.\n"
    "- причастие → одна строка; (о руке, ноге, языке) → одна строка.\n\n"
    "Отвечай СТРОГО одним JSON без markdown: "
    '{"translations": ["...", ...]}.'
)


def _strip_scope_parens(text):
    """Drop «(о каком-л. …)» scope notes; keep (о корове), (человека, …)."""
    t = _SCOPE_PAREN_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", t).strip(" ,")


def _strip_leading_pos_label(text):
    """Strip repeated leading POS/dict/dialect labels (техн., всг., conj, …)."""
    t = (text or "").strip()
    prefix_re = _label_prefix_re()
    while t:
        n = prefix_re.sub("", t, count=1).strip()
        if n == t:
            break
        t = n
    return t


def _strip_labels_across_commas(text):
    """«техн. нога, техн. опора» → «нога, опора» (labels on every chunk)."""
    parts = _split_commas_outside_parens(text)
    if len(parts) <= 1:
        return _strip_leading_pos_label(text)
    cleaned = [_strip_leading_pos_label(p) for p in parts]
    return ", ".join(c for c in cleaned if c)


def _is_mangled_paren_parallel(text):
    """
    True for expand artifacts like «нога (человека, нога животного)»
    where the head noun is wrongly repeated inside parentheses.
    """
    m = re.match(r"^([а-яё\-]+)\s*\((.+)\)\s*$", (text or "").strip(), re.I)
    if not m:
        return False
    head = m.group(1).lower()
    inner = m.group(2).lower()
    return bool(re.search(rf"(^|,\s*){re.escape(head)}\s+", inner))


def _split_commas_outside_parens(text):
    """Split on commas not inside (…); keep «нога (человека, животного)» intact."""
    parts = []
    buf = []
    depth = 0
    for ch in text or "":
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _starts_modifier_tail(part):
    """
    Continuation of an NP after a comma: participle, relative, or purpose clause.
    Not a new parallel synonym («опора», «при ком-л.»).
    """
    part = (part or "").strip()
    m = re.match(r"[а-яё\-]+", part.lower())
    if not m:
        return False
    w = m.group(0)
    if w in ("который", "которая", "которое", "которые", "где", "куда"):
        return True
    if w in ("для", "ради", "чтобы", "дабы"):
        return True
    if re.search(r"(?:анн|янн|енн|ённ|ованн|ёванн|ированн)(?:ый|ая|ое|ые|ой)$", w):
        return True
    if re.search(r"(?:вш|ущ|ющ|ащ|ящ)(?:ий|ая|ее|ие|ийся|аяся)$", w):
        return True
    if _gloss_chunk_word_count(part) >= 3 and re.search(
        r"(?:ый|ой|ая|ое|ые|ий|ье|тый|тая|тое|тые)$", w
    ):
        return True
    return False


def _is_parallel_synonym_chunk(part):
    """
    Short adjective/participle synonym, optionally with dict metalanguage
    («любящий что-л.»), not an NP attributive tail.
    """
    part = (part or "").strip()
    if not part or "(" in part:
        return False
    wc = _gloss_chunk_word_count(part)
    if wc == 0 or wc > 3:
        return False
    if re.search(
        r"(?:что|кого|чего|кому|чему|кем|чем|какой|какая|какое|какие)-л\.?\s*$",
        part,
        re.I,
    ):
        return True
    if wc > 2:
        return False
    m = re.match(r"[а-яё\-]+", part.lower())
    if not m:
        return False
    return bool(
        re.search(
            r"(?:ый|ой|ая|ое|ые|ий|ье|чий|жая|жий|ный|ная|ное|ные|"
            r"(?:вш|ущ|ющ|ащ|ящ)(?:ий|ая|ее|ие))$",
            m.group(0),
        )
    )


def _parallel_synonym_continuation(buf, part):
    """Participle-looking chunk is a parallel synonym of a short adj head."""
    if len(buf) != 1:
        return False
    head = buf[0]
    if not _is_parallel_synonym_chunk(head):
        return False
    return _is_parallel_synonym_chunk(part)


def _group_comma_gloss_chunks(text):
    """
    Split parallel synonyms, keep attributive/purpose tails with the head NP.

    «коник, широкая доска, прилегающая к печке, для удобства …»
    → ['коник', 'широкая доска, прилегающая к печке, для удобства …']
    «охочий, любящий что-л., любящий кого-л.» → three parallel groups.
    """
    parts = [p.strip() for p in _split_commas_outside_parens(text) if p.strip()]
    if not parts:
        return []
    groups = []
    buf = [parts[0]]
    for p in parts[1:]:
        if _starts_modifier_tail(p) and not _parallel_synonym_continuation(buf, p):
            buf.append(p)
        else:
            groups.append(", ".join(buf))
            buf = [p]
    groups.append(", ".join(buf))
    return groups


def _is_attributive_comma_phrase(text):
    """
    «верёвка, привязанная к люльке…» / multi-comma NP with participle+purpose.
    Not parallel synonyms («ручка, ухо», «нога, опора»).
    """
    parts = [p.strip() for p in _split_commas_outside_parens(text) if p.strip()]
    if len(parts) < 2:
        return False
    groups = _group_comma_gloss_chunks(text)
    if len(groups) < len(parts):
        return True
    if len(parts) != 2:
        return False
    left, right = parts
    if _gloss_chunk_word_count(left) > 3:
        return False
    if _gloss_chunk_word_count(right) < 2:
        return False
    return _starts_modifier_tail(right)


def _normalize_yo_to_e(text):
    """Match search query normalization (views.search: ё→е before ILIKE/FTS)."""
    return (text or "").translate(_YO_TO_E)


def _russian_text_after_spaced_tilde(part):
    """Russian gloss tail after «lemma ~ …» in one semicolon segment."""
    m = re.search(r"\s~\s+(.*)$", part or "", re.S)
    if not m:
        return ""
    t = TAG_RE.sub(" ", m.group(1))
    t = _LATIN_WORD_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" ,.")
    t = _strip_leading_pos_label(t)
    return t.strip()


def _is_possessive_collocation_phrase(text):
    """
    «берлога медведя», «логово волков» — употребление с род. падежом;
    не «длинная дорога» (прилагательное + существительное).
    """
    words = re.findall(r"[а-яё\-]+", (text or "").lower())
    if len(words) != 2:
        return False
    if re.search(r"(ый|ой|ий|ая|ое|ые|ее|ие)$", words[0]):
        return False
    # Genitive-like endings: медведя, волков, колокола, сети, …
    return bool(re.search(r"(ы|и|ов|ей|я|а|ам|ах|ю)$", words[1]))


# Adj+N collocations kept as gloss («длинная дорога», «крепкий запах»).
_GLOSS_COLLOCATION_ADJ_STEMS = (
    "длинн",
    "прям",
    "коротк",
    "узк",
    "широк",
    "крепк",
    "крут",
    "кос",
    "гол",
    "гладк",
    "остр",
    "туп",
    "высок",
    "низк",
    "глубок",
    "мелк",
)


def _is_adj_noun_phrase(text):
    words = re.findall(r"[а-яё\-]+", (text or "").lower())
    if len(words) != 2:
        return False
    return bool(re.search(r"(ый|ой|ий|ая|ое|ые|ее|ие)$", words[0]))


def _is_gloss_adj_noun_collocation(text):
    """Fixed dictionary phrase, not a running example («длинная дорога»)."""
    if not _is_adj_noun_phrase(text):
        return False
    first = re.findall(r"[а-яё\-]+", (text or "").lower())[0]
    return any(first.startswith(stem) for stem in _GLOSS_COLLOCATION_ADJ_STEMS)


def _is_evaluative_adj_noun_phrase(text):
    """
    «хорошее настроение», «большие уши» — пример с оценочным прилагательным;
    не «длинная дорога», «крепкий запах».
    """
    return _is_adj_noun_phrase(text) and not _is_gloss_adj_noun_collocation(text)


def _is_illustration_segment(part):
    """Semicolon segment that is a Karelian example, not dictionary gloss."""
    part = (part or "").strip()
    if not part:
        return True
    # «~an'e ухо» — headword slot + Russian gloss (apostrophe U+2019 or ASCII).
    if _HEADWORD_SLOT_RE.match(part):
        return False
    # «~vavot нарезать» / «~ vavot …» — Karelian example line, not headword slot.
    if re.match(rf"^~\s*[{_KRL_LETTER}][{_KRL_LETTER}\-]*\s+[а-яё]", part, re.I):
        return True
    # «~ vavot нарезать борозды» — spaced tilde + Karelian word.
    if re.match(rf"^~\s+[{_KRL_LETTER}]", part):
        return True
    # Spaced tilde: «olla ~ быть» (gloss) vs «ken mahtaw el'ia, že on ~ …» (example).
    m = re.search(r"\s~\s+", part)
    if m:
        before = part[: m.start()].strip()
        after = part[m.end() :].strip()
        latin_before = _LATIN_WORD_RE.findall(before)
        latin_after = _LATIN_WORD_RE.findall(after)
        if latin_before and latin_after:
            return True
        if len(latin_before) >= 2:
            return True
        if len(latin_before) == 1:
            w = latin_before[0].lower().rstrip(".")
            if w in _gloss_label_word_set():
                return False
            # «vägövä ~ крепкое пиво», «pit'kä ~ длинная дорога» — Karelian
            # example line, not a gloss (collocation whitelist must not override).
            if w not in {"olla", "lienee", "ei", "on"}:
                return True
        rus = _russian_text_after_spaced_tilde(part)
        # Headword / copula «olla ~ длинная дорога» — keep fixed gloss collocations.
        if _is_gloss_adj_noun_collocation(rus):
            return False
        if _is_possessive_collocation_phrase(rus):
            return True
        if _is_evaluative_adj_noun_phrase(rus):
            return True
        return False

    # Ignore Latin/Karelian inside (…): grammar notes often cite forms
    # («l’ienöw», «l’iew») without turning the gloss into an illustration.
    probe = _PAREN_RE.sub(" ", part)
    latin_words = _LATIN_WORD_RE.findall(probe)
    if not latin_words:
        return False
    first = latin_words[0].lower().rstrip(".")
    if first in _gloss_label_word_set():
        return False
    if len(latin_words) >= 2:
        return True
    if probe.lower().lstrip().startswith(latin_words[0].lower()):
        return True
    return False


def _is_crossref_text(text):
    """True if text is only a see/cf pointer (см./ср.), not a translation."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = t.strip(" .,'\"«»")
    if not t:
        return False
    if t.lower() in _CROSSREF_TOKENS:
        return True
    if re.fullmatch(r"(?:см|ср)\.?", t, re.I):
        return True
    if not re.search(r"(?:^|\s)(?:см|ср)\.?", t, re.I):
        return False
    words = [
        w for w in re.findall(r"[а-яё]+", t, re.I) if w.lower() not in _CROSSREF_TOKENS
    ]
    return len(words) == 0


def _is_crossref_only(html_chunk):
    """Entire <li>/block is a see/cf pointer, optionally after POS/dialect labels."""
    raw = html_chunk or ""
    # Drop leading <i>s</i> <i>всг.</i> <i>см.</i> … label run.
    stripped = re.sub(
        r"^(?:\s*<i[^>]*>[\s\S]*?</i>)+",
        "",
        raw,
        count=1,
        flags=re.I,
    )
    check = stripped if stripped != raw else raw
    if re.match(
        r"\s*(?:<i[^>]*>\s*)?(?:см|ср)\.?\s*(?:</i>)?\s*",
        check,
        re.I,
    ):
        rest = re.sub(
            r"^\s*(?:<i[^>]*>\s*)?(?:см|ср)\.?\s*(?:</i>)?\s*",
            "",
            check,
            count=1,
            flags=re.I,
        )
        # Pure «см. lemma» or «см. lemma; only Karelian examples».
        if not re.search(r"[а-яё]{3,}", TAG_RE.sub(" ", rest), re.I):
            return True
    t = TAG_RE.sub(" ", raw)
    t = re.sub(r"\s+", " ", t).strip()
    t = _strip_leading_pos_label(t)
    t = _LATIN_WORD_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" .'")
    return _is_crossref_text(t)


def _is_grammar_paren(inner):
    low = (inner or "").lower()
    return any(h in low for h in _GRAMMAR_PAREN_HINTS)


def _strip_grammar_parens(text):
    """Remove grammar-only parentheticals; keep semantic ones like (по вкусу)."""

    def repl(m):
        return "" if _is_grammar_paren(m.group(1)) else m.group(0)

    t = _PAREN_RE.sub(repl, text)
    return re.sub(r"\s+", " ", t).strip(" \t,;")


def _normalize_gloss_segment(part):
    """Drop leading «: olla ~» prefix; keep Russian after spaced tilde."""
    part = (part or "").strip().lstrip(":").strip()
    if " ~ " in part:
        part = part.split(" ~ ", 1)[1].strip()
    else:
        m = re.match(
            rf"^~[{_KRL_LETTER}{_KRL_APOS}\-]*[{_KRL_APOS}][{_KRL_LETTER}{_KRL_APOS}\-]*\s+(.+)$",
            part,
        )
        if m:
            part = m.group(1).strip()
    return part


def _is_likely_russian_infinitive(word):
    """True for «получаться», «идти», «жечь» — not nouns like «деготь», «печали»."""
    w = (word or "").lower()
    if not w:
        return False
    # High-frequency nouns ending like infinitives (-оть / -еть / -ть).
    if w in {
        "деготь",
        "ноготь",
        "локоть",
        "коготь",
        "ломоть",
        "лапоть",
        "живот",
    }:
        return False
    return bool(re.search(r"(?:ться|тись|ти|чь|[аеиоуыя]ть)$", w))


_DISCOURSE_COMMA_PART_RE = re.compile(
    r"^(?:например|напр\.?|т\.?\s?е\.?|тоесть)$",
    re.I,
)


def _expand_shared_object_pair(left, right):
    """
    «вбить, вогнать гвоздь» → «вбить гвоздь, вогнать гвоздь».
    Shared object on the last multi-word verb phrase.
    """
    lw = _words_outside_parens(left)
    rw = _words_outside_parens(right)
    if len(lw) != 1 or len(rw) < 2:
        return None
    if not _is_likely_russian_infinitive(lw[0]):
        return None
    if not _is_likely_russian_infinitive(rw[0]):
        return None
    obj = " ".join(re.split(r"\s+", right.strip())[1:]).strip()
    if not obj or "(" in left or "(" in right:
        return None
    return f"{lw[0]} {obj}, {right.strip()}"


def _words_outside_parens(text):
    """Cyrillic tokens outside (…) — head of «всходить (о светилах)» is one word."""
    outer = _PAREN_RE.sub(" ", text or "")
    return re.findall(r"[а-яё\-]+", outer.lower())


def _expand_comma_parallel(text):
    """
    «быть в обиде, печали» → «быть в обиде, быть в печали» (ellipsis in gloss).

    Do NOT expand independent parallel senses («идти на лад, получаться»):
    the second item is a full infinitive, not a noun completing the frame.
    Commas inside (…) are not split points.
    Do NOT use / extend prefixes through parentheticals («подниматься (о тесте)»).
    Do NOT expand across «например» («рыбы, например, сома»).
    «вбить, вогнать гвоздь» → shared object on both verbs.
    """
    parts = _split_commas_outside_parens(text)
    if len(parts) < 2:
        return text
    if any(_DISCOURSE_COMMA_PART_RE.match(p.strip()) for p in parts):
        return text
    if len(parts) == 2:
        shared = _expand_shared_object_pair(parts[0], parts[1])
        if shared:
            return shared
    out = []
    prefix = None
    for p in parts:
        if not p:
            continue
        # Chunks with (…) are whole senses/scopes — never ellipsis glue sources.
        if "(" in p or ")" in p:
            out.append(p)
            prefix = None
            continue
        words = _words_outside_parens(p)
        if len(words) >= 2:
            prefix = " ".join(words[:-1])
            out.append(p)
        elif len(words) == 1 and prefix and not _is_likely_russian_infinitive(words[0]):
            out.append(f"{prefix} {p}")
        else:
            out.append(p)
            prefix = None
    return ", ".join(out)


def _gloss_segments(text):
    """
    Keep semicolon-separated gloss fragments; drop illustration tails.

    Dictionary layout: Russian gloss first; once a Karelian example starts,
    everything after (including pure-Russian tails) is illustration.
    """
    parts = [p.strip() for p in text.split(";")]
    kept = []
    for part in parts:
        if not part:
            continue
        # Strip grammar notes first: they may embed Karelian paradigm forms
        # that would otherwise trip the illustration gate on the whole segment.
        part = _strip_grammar_parens(part)
        if not part:
            continue
        if _is_illustration_segment(part):
            break
        part = _normalize_gloss_segment(part)
        if not part or _is_crossref_text(part):
            continue
        if ":" in part:
            label, _, tail = part.partition(":")
            label_cyr = len(re.findall(r"[а-яё]", label, re.I))
            tail_cyr = len(re.findall(r"[а-яё]", tail, re.I))
            if label_cyr <= 2 and tail_cyr >= 2:
                part = tail.strip()
        cyr = len(re.findall(r"[а-яё]", part, re.I))
        lat = len(re.findall(r"[a-z]", part, re.I))
        if lat > 2 and cyr <= lat:
            break
        cleaned = _LATIN_WORD_RE.sub(" ", part)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
        cleaned = _strip_leading_pos_label(cleaned)
        cleaned = _expand_comma_parallel(cleaned)
        cleaned = _normalize_yo_to_e(cleaned)
        if cleaned and re.search(r"[а-яё]", cleaned, re.I):
            kept.append(cleaned)
    return kept


def _russian_gloss_chunk(html_chunk):
    """Russian gloss text from one block, strip tags and Karelian tail."""
    if not html_chunk or _is_crossref_only(html_chunk):
        return ""
    t = TAG_RE.sub(" ", html_chunk)
    t = re.sub(r"\s+", " ", t).strip()
    if "◊" in t:
        t = t.split("◊", 1)[0].strip()
    t = _strip_leading_pos_label(t)
    t = t.lstrip(":").strip()
    segments = _gloss_segments(t)
    if segments:
        return "; ".join(segments)
    if _LATIN_WORD_RE.search(t):
        return ""
    t = _LATIN_WORD_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" \t;,")
    t = _strip_grammar_parens(t)
    if len(t) < 2 or _is_crossref_text(t):
        return ""
    if not re.search(r"[а-яёА-ЯЁ]", t):
        return ""
    return t


def gloss_senses_from_html(html):
    """
    Russian gloss per dictionary sense: one string per <li>, no illustrations.

    Falls back to a single block after </b> when there is no <ol>.
    """
    if not html:
        return []
    senses = []
    if re.search(r"<li[\s>]", html, re.I):
        for m in re.finditer(r"<li[^>]*>(.*?)</li>", html, re.I | re.S):
            g = _russian_gloss_chunk(m.group(1))
            if g:
                senses.append(g)
        return senses
    rest = re.sub(r"^[\s\S]*?</b>\s*", "", html, count=1, flags=re.I)
    rest = re.sub(r"^(?:<i[^>]*>[\s\S]*?</i>\s*)+", "", rest, count=1, flags=re.I)
    g = _russian_gloss_chunk(rest)
    return [g] if g else []


def _phraseme_senses_from_html(html):
    """Russian phrasemes from ◊ blocks (~ русский текст after lozenge)."""
    if not html or "◊" not in html:
        return []
    phrases = set()
    for m in re.finditer(r"◊([\s\S]*?)(?=</li>|$)", html, re.I):
        block = TAG_RE.sub(" ", m.group(1))
        for pm in re.finditer(
            r"~\s*([а-яё][^;]*?)(?:\s+[A-Za-z''\-]|;|$)", block, re.I
        ):
            phrase = _normalize_yo_to_e(re.sub(r"\s+", " ", pm.group(1)).strip(" ,."))
            if phrase and re.search(r"[а-яё]{2,}", phrase, re.I):
                phrases.add(phrase)
        for pm in re.finditer(
            r";\s*([а-яё][а-яё\s\-]+?)(?:\s+[A-Za-z]|;|$)", block, re.I
        ):
            phrase = _normalize_yo_to_e(re.sub(r"\s+", " ", pm.group(1)).strip(" ,."))
            if phrase and len(re.findall(r"[а-яё]+", phrase.lower())) >= 2:
                phrases.add(phrase)
    return sorted(phrases, key=str.lower)


def addendum_gloss_senses_for(article):
    """Russian gloss per <li> from ArticleAddition blocks, in id order."""
    senses = []
    for add in article.additions.all().order_by("id"):
        senses.extend(gloss_senses_from_html(add.article_html or ""))
    return senses


def _merge_phraseme_senses(main_html, addition_htmls):
    seen = set()
    out = []
    for html in [main_html] + list(addition_htmls):
        for phrase in _phraseme_senses_from_html(html or ""):
            key = phrase.lower()
            if key not in seen:
                seen.add(key)
                out.append(phrase)
    return out


def all_gloss_senses(art_input):
    """Main + addendum gloss lists (for post-LLM sanitize)."""
    return (art_input.get("gloss_senses") or []) + (
        art_input.get("addendum_gloss_senses") or []
    )


def pos_tags_for(article):
    """Russian POS tag names (Tag.type == part of speech) for the article."""
    return list(
        Tag.objects.filter(
            articleindextag__article=article,
            type=2,
        ).values_list("name", flat=True)
    )


# Tag.tag (type=2) → coarse Russian POS for the LLM (lemma word class).
_POS_ROLE_BY_TAG = {
    "s": "существительное",
    "v": "глагол",
    "a": "прилагательное",
    "adv": "наречие",
    "pron": "местоимение",
    "num": "числительное",
    "conj": "союз",
    "particl": "частица",
    "postp": "послелог",
    "prep": "предлог",
    "interj": "междометие",
}

# Secondary POS marks (aspect etc.) — not the lemma's main word class.
_POS_ROLE_SECONDARY = frozenset(
    {
        "freq",
        "mom",
        "caus",
        "descr",
        "refl",
        "impers",
        "imper",
        "comp",
        "superl",
        "pl",
        "sing",
        "coll",
        "com",
        "def",
        "intens",
        "demonstr",
        "indef",
        "interr",
        "pers",
        "relat",
        "indecl",
    }
)


def _pos_role_from_tag_row(tag, name):
    """Map one Tag.type=2 row to a coarse role, or None if secondary/unknown."""
    code = (tag or "").strip().lower()
    if code in _POS_ROLE_SECONDARY:
        return None
    if code in _POS_ROLE_BY_TAG:
        return _POS_ROLE_BY_TAG[code]
    low = (name or "").lower()
    for needle, role in (
        ("существительн", "существительное"),
        ("глагол", "глагол"),
        ("прилагательн", "прилагательное"),
        ("нареч", "наречие"),
        ("местоимен", "местоимение"),
        ("числительн", "числительное"),
        ("союз", "союз"),
        ("частиц", "частица"),
        ("послелог", "послелог"),
        ("предлог", "предлог"),
        ("междомет", "междометие"),
    ):
        if needle in low:
            return role
    return None


def pos_roles_for(article):
    """
    Coarse POS roles for the lemma from Tag.type=2 (s/v/a/…), deduped.

    Secondary marks (freq, mom, …) are omitted — they are not the word class.
    """
    rows = Tag.objects.filter(
        articleindextag__article=article,
        type=2,
    ).values_list("tag", "name")
    out = []
    seen = set()
    for tag, name in rows:
        role = _pos_role_from_tag_row(tag, name)
        if not role or role in seen:
            continue
        seen.add(role)
        out.append(role)
    return out


def is_service_word_article(pos_tags):
    """True if any POS tag marks a function word (conjunction, particle, …)."""
    for name in pos_tags:
        lower = (name or "").lower()
        if any(kw in lower for kw in SERVICE_POS_KEYWORDS):
            return True
    return False


def build_cleanup_input(article):
    """
    Payload: headword, raw translations, POS, gloss_senses (no illustrations),
    addendum_gloss_senses from ArticleAddition if any.
    """
    translations = list(
        ArticleIndexTranslate.objects.filter(article=article)
        .exclude(rus_word__isnull=True)
        .exclude(rus_word="")
        .values_list("rus_word", flat=True)
    )
    tags = pos_tags_for(article)
    roles = pos_roles_for(article)
    main_html = article.article_html or ""
    addition_htmls = [
        add.article_html or "" for add in article.additions.all().order_by("id")
    ]
    return {
        "word": article.word,
        "translations": translations,
        "gloss_senses": gloss_senses_from_html(main_html),
        "addendum_gloss_senses": addendum_gloss_senses_for(article),
        "dict_labels": dict_label_tags_from_db(),
        "pos": roles[0] if len(roles) == 1 else roles,
        "pos_tags": tags,
        "is_service_word": is_service_word_article(tags),
        "article_html": main_html,
    }


def build_cleanup_user_prompt(art_input):
    payload = {k: v for k, v in art_input.items() if k != "article_html"}
    return (
        "Статья:\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\nВерни очищенный список translations."
    )


def build_cleanup_review_user_prompt(art_input, draft_translations):
    """Second-pass payload: draft + gloss context (no article_html)."""
    payload = {
        "word": art_input.get("word"),
        "pos": art_input.get("pos"),
        "pos_tags": art_input.get("pos_tags"),
        "is_service_word": art_input.get("is_service_word"),
        "dict_labels": art_input.get("dict_labels"),
        "gloss_senses": art_input.get("gloss_senses"),
        "addendum_gloss_senses": art_input.get("addendum_gloss_senses"),
        "original_translations": art_input.get("translations"),
        "draft_translations": draft_translations,
    }
    return (
        "Черновик индекса и контекст статьи:\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\nВерни исправленный список translations."
    )


def _expand_parallel_verb_fragments(translations):
    """
    «делать более лёгким» + «менее трудным» → prepend shared verb to bare comparatives.
    """
    if not translations:
        return translations
    shared_verb = None
    for t in translations:
        m = re.match(r"^([а-яё]+)\s+(более|менее)\s+", t, re.I)
        if m:
            shared_verb = m.group(1).lower()
            break
    if not shared_verb:
        return translations
    out = []
    for t in translations:
        if re.match(r"^(более|менее)\s+", t, re.I) and not re.match(
            r"^[а-яё]+\s+(более|менее)\s+", t, re.I
        ):
            t = f"{shared_verb} {t}"
        out.append(t)
    return out


_I_PRO_PARALLEL_RE = re.compile(
    r"([а-яё][^,;]+?\s)([а-яё]+),\s*([а-яё]+)\s+и\s+пр\.?",
    re.I,
)


def _phrases_from_i_pro_parallel(gloss_senses):
    """«лучины для плетения лаптей, корзин и пр.» → full phrases for each tail."""
    phrases = []
    seen = set()
    for sense in gloss_senses or []:
        for m in _I_PRO_PARALLEL_RE.finditer(sense):
            prefix = m.group(1)
            for tail in (m.group(2).strip(), m.group(3).strip()):
                phrase = _normalize_yo_to_e(
                    re.sub(r"\s+", " ", (prefix + tail).strip())
                )
                key = phrase.lower()
                if key not in seen:
                    seen.add(key)
                    phrases.append(phrase)
    return phrases


def _ensure_i_pro_parallel_phrases(translations, gloss_senses):
    """Add full parallel phrases from gloss «… A, B и пр.» tails."""
    if not gloss_senses:
        return translations
    existing = {t.lower() for t in translations}
    out = list(translations)
    for phrase in _phrases_from_i_pro_parallel(gloss_senses):
        if phrase.lower() not in existing:
            out.append(phrase)
            existing.add(phrase.lower())
    return out


def _drop_i_pro_tail_fragments(translations):
    """Remove «корзин и пр.»-style tails without shared prefix."""
    return [t for t in translations if not re.search(r"\s+и\s+пр\.?\s*$", t, re.I)]


def _looks_like_ellipsis_frame(chunk):
    """True for «быть в обиде»-style frames that can take a bare noun tail."""
    words = re.findall(r"[а-яё\-]+", (chunk or "").lower())
    if len(words) < 2:
        return False
    prep = {
        "в",
        "во",
        "на",
        "о",
        "об",
        "обо",
        "с",
        "со",
        "к",
        "ко",
        "у",
        "от",
        "из",
        "по",
        "за",
        "под",
        "при",
        "над",
        "перед",
        "через",
    }
    return any(w in prep for w in words[:-1])


def gloss_listed_single_word_forms(gloss_senses):
    """
    Explicit single-word items in gloss comma-lists («логово, лежбище; глаз, …»).

    Skips ellipsis tails («быть в обиде, печали») and words inside phrases.
    Keeps true parallels after fixed phrases («да и, и»).
    """
    forms = []
    seen = set()
    for sense in gloss_senses or []:
        semicolon_parts = [p.strip() for p in (sense or "").split(";") if p.strip()]
        for seg_idx, segment in enumerate(semicolon_parts):
            if _NAPRIMER_RE.search(segment):
                continue
            seen_ellipsis_frame = False
            chunks = []
            for chunk in _split_commas_outside_parens(segment):
                chunk = _strip_leading_pos_label(chunk.strip())
                chunk = _strip_grammar_parens(chunk)
                chunk = re.sub(r"\s+", " ", chunk).strip()
                if chunk and re.search(r"[а-яё]", chunk, re.I):
                    chunks.append(chunk)
            if len(chunks) >= 2:
                for chunk in chunks:
                    words = re.findall(r"[а-яё\-]+", chunk.lower())
                    if len(words) >= 2:
                        if _looks_like_ellipsis_frame(chunk):
                            seen_ellipsis_frame = True
                        continue
                    if len(words) != 1:
                        continue
                    # Ellipsis nouns after a phrase («…, печали») — skip;
                    # parallel infinitives («идти на лад, получаться») — keep;
                    # bare «и» after «да и» — keep.
                    if seen_ellipsis_frame and not _is_likely_russian_infinitive(
                        words[0]
                    ):
                        continue
                    form = _normalize_yo_to_e(words[0])
                    key = form.lower()
                    if key in _CROSSREF_TOKENS or key in seen:
                        continue
                    seen.add(key)
                    forms.append(form)
            elif len(chunks) == 1 and len(semicolon_parts) >= 2 and seg_idx == 0:
                words = re.findall(r"[а-яё\-]+", chunks[0].lower())
                if len(words) == 1:
                    form = _normalize_yo_to_e(words[0])
                    key = form.lower()
                    if key in _CROSSREF_TOKENS or key in seen:
                        continue
                    seen.add(key)
                    forms.append(form)
    return forms


def _gloss_protected_lemmas(gloss_senses):
    """Lemma keys that must not be dropped as subsumed word fragments."""
    protected = {s.lower() for s in _gloss_standalone_equivalents(gloss_senses)}
    for form in gloss_listed_single_word_forms(gloss_senses):
        protected.add(form.lower())
    return protected


def _gloss_standalone_equivalents(gloss_senses):
    """
    Single-word equivalents explicitly listed in gloss (comma/semicolon chunks).
    «быть, существовать» → ['быть', 'существовать']; protects olla-like lemmas.
    Skips lone words in parallel lists («…, печали» after «быть в обиде»).
    """
    forms = []
    seen = set()
    for sense in gloss_senses or []:
        chunks = []
        for segment in (sense or "").split(";"):
            for chunk in _split_commas_outside_parens(segment):
                chunk = _strip_leading_pos_label(chunk.strip())
                chunk = _strip_grammar_parens(chunk)
                chunk = re.sub(r"\s+", " ", chunk).strip()
                if chunk and re.search(r"[а-яё]", chunk, re.I):
                    chunks.append(chunk)
        has_multi = any(len(re.findall(r"[а-яё\-]+", c.lower())) >= 2 for c in chunks)
        for chunk in chunks:
            if len(re.findall(r"[а-яё\-]+", chunk.lower())) != 1:
                continue
            if has_multi:
                continue
            form = _normalize_yo_to_e(chunk)
            key = form.lower()
            if key in _CROSSREF_TOKENS or key in seen:
                continue
            seen.add(key)
            forms.append(form)
    return forms


def _gloss_chunk_word_count(chunk):
    """Word count ignoring parenthetical qualifiers."""
    without_parens = _PAREN_RE.sub("", chunk or "").strip()
    return len(re.findall(r"[а-яё\-]+", without_parens.lower()))


def _gloss_comma_list_segments(gloss_senses):
    """Comma-list gloss fragments (parallel groups; attributive tails stay glued)."""
    segments = []
    for sense in gloss_senses or []:
        for part in (sense or "").split(";"):
            part = re.sub(r"\s+", " ", part.strip())
            part = re.sub(r"^~+\s*", "", part).strip()
            part = _strip_leading_pos_label(part)
            if not part or not re.search(r"[а-яё]", part, re.I):
                continue
            if _NAPRIMER_RE.search(part):
                continue
            groups = _group_comma_gloss_chunks(part)
            if len(groups) >= 2:
                segments.append(_normalize_yo_to_e(part))
    return segments


def _expand_comma_gloss_list_lines(translations, gloss_senses):
    """
    Split glued gloss comma-lists into parallel index lines.

    Uses grouped chunks so «доска, прилегающая к печке, для …» stays one line.
    Also splits short synonym glues («охочий, любящий что-л., …») when each
    chunk appears in gloss_senses.
    """
    if not gloss_senses:
        return translations
    gloss_lists = {s.lower() for s in _gloss_comma_list_segments(gloss_senses)}
    gloss_blob = " | ".join(g.lower() for g in gloss_senses)
    out = []
    seen = set()
    for t in translations:
        tn = _normalize_yo_to_e(t).lower()
        groups = [re.sub(r"\s+", " ", c.strip()) for c in _group_comma_gloss_chunks(t)]
        groups = [c for c in groups if c]
        should_split = False
        if tn in gloss_lists and len(groups) >= 2:
            should_split = True
        elif (
            len(groups) >= 2
            and not _is_attributive_comma_phrase(t)
            and all(_gloss_chunk_word_count(g) <= 4 for g in groups)
            and all(g.lower() in gloss_blob for g in groups)
        ):
            should_split = True
        if should_split:
            for chunk in groups:
                piece = _strip_leading_pos_label(chunk)
                if not piece or not re.search(r"[а-яё]", piece, re.I):
                    continue
                # Synonym list: «ушко (у разных предметов)» → bare «ушко».
                # Keep about-scopes: «всходить (о светилах)».
                if (
                    "(" in piece
                    and len(_words_outside_parens(piece)) == 1
                    and _parse_about_scope_line(piece) is None
                ):
                    piece = _PAREN_RE.sub("", piece).strip()
                if not piece or not re.search(r"[а-яё]", piece, re.I):
                    continue
                c = _normalize_yo_to_e(piece)
                key = c.lower()
                if key in seen or key in _CROSSREF_TOKENS:
                    continue
                out.append(c)
                seen.add(key)
            continue
        if tn not in seen:
            out.append(t)
            seen.add(tn)
    return out


def _gloss_listed_phrases(gloss_senses):
    """
    Multi-word gloss chunks from comma/semicolon lists (grouped parallels).
    """
    phrases = []
    seen = set()
    for sense in gloss_senses or []:
        for segment in (sense or "").split(";"):
            segment = _strip_leading_pos_label(segment.strip())
            segment = _strip_grammar_parens(segment)
            segment = re.sub(r"\s+", " ", segment).strip()
            if not segment:
                continue
            # «рыбы, например, сома» — leave for LLM; do not force mangled chunks.
            if _NAPRIMER_RE.search(segment):
                continue
            groups = []
            for chunk in _group_comma_gloss_chunks(segment):
                chunk = _strip_leading_pos_label(chunk.strip())
                chunk = _strip_grammar_parens(chunk)
                chunk = re.sub(r"\s+", " ", chunk).strip()
                if chunk and re.search(r"[а-яё]", chunk, re.I):
                    groups.append(chunk)
            if len(groups) >= 2:
                if all(
                    _gloss_chunk_word_count(c) <= 1 and "," not in c for c in groups
                ):
                    continue
                for chunk in groups:
                    if _gloss_chunk_word_count(chunk) >= 2 or "," in chunk:
                        phrase = _normalize_yo_to_e(chunk)
                        key = phrase.lower()
                        if key not in seen:
                            seen.add(key)
                            phrases.append(phrase)
            elif len(groups) == 1:
                words = re.findall(r"[а-яё\-]+", groups[0].lower())
                if len(words) >= 2 or "," in groups[0]:
                    phrase = _normalize_yo_to_e(groups[0])
                    key = phrase.lower()
                    if key not in seen:
                        seen.add(key)
                        phrases.append(phrase)
    return phrases


def _ensure_gloss_listed_phrases(translations, gloss_senses):
    """Re-add multi-word gloss phrases dropped or truncated by LLM."""
    if not gloss_senses:
        return translations
    existing = {t.lower() for t in translations}
    out = list(translations)
    for phrase in _gloss_listed_phrases(gloss_senses):
        phrase = _strip_scope_parens(phrase)
        pl = phrase.lower()
        if not pl or pl in existing:
            continue
        out.append(phrase)
        existing.add(pl)
    return _drop_attributive_comma_fragments(out, gloss_senses)


def _attributive_gloss_phrases(gloss_senses):
    """NP groups that contain glued participle/purpose tails (have internal commas)."""
    phrases = []
    seen = set()
    for sense in gloss_senses or []:
        for segment in (sense or "").split(";"):
            segment = _strip_leading_pos_label(segment.strip())
            segment = _strip_grammar_parens(segment)
            segment = re.sub(r"\s+", " ", segment).strip()
            if not segment:
                continue
            for group in _group_comma_gloss_chunks(segment):
                group = re.sub(r"\s+", " ", group.strip())
                if "," not in group:
                    continue
                phrase = _normalize_yo_to_e(group)
                key = phrase.lower()
                if key not in seen:
                    seen.add(key)
                    phrases.append(phrase)
    return phrases


def _drop_attributive_comma_fragments(translations, gloss_senses):
    """Drop «веревка» / «привязанная…» when full attributive gloss phrase exists."""
    fulls = _attributive_gloss_phrases(gloss_senses)
    if not fulls:
        return translations
    fragment_keys = set()
    for full in fulls:
        for chunk in _split_commas_outside_parens(full):
            chunk = _normalize_yo_to_e(chunk.strip()).lower()
            if chunk:
                fragment_keys.add(chunk)
    full_keys = {f.lower() for f in fulls}
    out = []
    for t in translations:
        tl = t.lower()
        if tl in full_keys:
            out.append(t)
            continue
        if tl in fragment_keys:
            continue
        # Shorter head of a longer attributive group («доска, прилегающая…»
        # vs «доска, прилегающая…, для …»). Not «нога» vs «нога (…)».
        if any(
            len(_split_commas_outside_parens(fl)) >= 2
            and (fl.startswith(tl + ", ") or fl.startswith(tl + " "))
            for fl in full_keys
            if fl != tl
        ):
            continue
        # Same NP head as a longer attributive chain («широкая доска для …»
        # vs «широкая доска, прилегающая…, для …»).
        t_head = " ".join(re.findall(r"[а-яё\-]+", tl)[:2])
        if t_head and any(
            len(_split_commas_outside_parens(fl)) >= 2
            and " ".join(re.findall(r"[а-яё\-]+", fl)[:2]) == t_head
            and fl != tl
            and len(fl) > len(tl)
            for fl in full_keys
        ):
            continue
        out.append(t)
    # Ensure full phrases remain even if only fragments were present.
    existing = {t.lower() for t in out}
    for full in fulls:
        if full.lower() not in existing:
            out.append(full)
            existing.add(full.lower())
    return out


def _about_scope_items(inner):
    """
    «о руке, ноге, языке» → ('о', ['руке', 'ноге', 'языке']).
    Only о/об/про scopes (not «по вкусу», «человека, животного»).
    """
    inner = (inner or "").strip()
    m = re.match(r"^(о|об|про)\s+(.+)$", inner, re.I)
    if not m:
        return None
    prep = m.group(1).lower()
    parts = [p.strip() for p in m.group(2).split(",") if p.strip()]
    if not parts:
        return None
    return prep, parts


def _parse_about_scope_line(text):
    """«отняться … (о руке)» → (head, prep, [items]) or None."""
    m = re.match(
        r"^(.+?)\s*\(\s*((?:о|об|про)\s+[^)]+)\)\s*$",
        (text or "").strip(),
        re.I,
    )
    if not m:
        return None
    head = m.group(1).strip()
    scope = _about_scope_items(m.group(2))
    if not head or not scope:
        return None
    prep, items = scope
    return head, prep, items


def _collapse_about_scope_parallels(translations):
    """
    Merge «head (о A)», «head (о B)», «head (о A, B)» → one «head (о A, B)».

    Keeps a single combined parenthetical; drops per-item duplicates.
    """
    if not translations or len(translations) < 2:
        return translations

    parsed = []
    for t in translations:
        parsed.append(_parse_about_scope_line(t))

    by_head = {}
    for i, p in enumerate(parsed):
        if not p:
            continue
        key = p[0].lower()
        by_head.setdefault(key, []).append(i)

    drop = set()
    replace_at = {}
    for indices in by_head.values():
        if len(indices) < 2:
            continue
        prep = parsed[indices[0]][1]
        head = parsed[indices[0]][0]
        items = []
        seen_item = set()
        # Prefer order from an already-combined line, then appearance order.
        multi_first = sorted(
            indices, key=lambda i: (0 if len(parsed[i][2]) >= 2 else 1, i)
        )
        for i in multi_first:
            prep = parsed[i][1]
            for it in parsed[i][2]:
                ik = it.lower()
                if ik in seen_item:
                    continue
                seen_item.add(ik)
                items.append(it)
        if len(items) < 2:
            continue
        combined = f"{head} ({prep} {', '.join(items)})"
        for i in indices:
            drop.add(i)
        replace_at[indices[0]] = _normalize_yo_to_e(combined)

    if not drop:
        return translations

    out = []
    seen = set()
    for i, t in enumerate(translations):
        if i in drop:
            if i in replace_at:
                c = replace_at[i]
                key = c.lower()
                if key not in seen:
                    out.append(c)
                    seen.add(key)
            continue
        key = t.lower()
        if key not in seen:
            out.append(t)
            seen.add(key)
    return out


def _drop_false_ellipsis_expansions(translations):
    """
    Drop «идти на получаться» when «идти на лад» and bare «получаться» both exist.

    False product of noun-ellipsis expand applied to parallel infinitives.
    """
    if not translations:
        return translations
    lowers = [t.lower() for t in translations]
    drop = set()
    for i, t in enumerate(lowers):
        words = re.findall(r"[а-яё\-]+", t)
        if len(words) < 2 or not _is_likely_russian_infinitive(words[-1]):
            continue
        bare = words[-1]
        if bare not in lowers:
            continue
        prefix = " ".join(words[:-1])
        for j, other in enumerate(lowers):
            if i == j or not other.startswith(prefix + " "):
                continue
            other_words = re.findall(r"[а-яё\-]+", other)
            if len(other_words) >= 2 and other_words[-1] != bare:
                drop.add(i)
                break
    return [t for i, t in enumerate(translations) if i not in drop]


def _drop_truncated_gloss_phrases(translations, gloss_senses):
    """Drop «при» when gloss lists «при ком-л.»; keep short if long is only + (…)."""
    phrases = _gloss_listed_phrases(gloss_senses)
    if not phrases:
        return translations
    protected = _gloss_protected_lemmas(gloss_senses)
    phrase_lowers = [p.lower() for p in phrases]
    out = []
    for t in translations:
        tl = t.lower()
        if tl in protected:
            out.append(t)
            continue
        drop = False
        for pl in phrase_lowers:
            if pl == tl or not pl.startswith(tl + " "):
                continue
            rest = pl[len(tl) :].strip()
            # «X (о каком-л. …)» is not a longer synonym — keep short X.
            if (
                rest.startswith("(")
                and rest.endswith(")")
                and rest.count("(") == 1
                and rest.count(")") == 1
            ):
                continue
            drop = True
            break
        if not drop:
            out.append(t)
    return out


def _drop_subsumed_auxiliaries(translations, gloss_senses=None):
    """Remove lone aux token if a longer list entry contains it as a word."""
    if not translations:
        return translations
    protected = {s.lower() for s in _gloss_standalone_equivalents(gloss_senses)}
    lower_phrases = [t.lower() for t in translations]
    drop = set()
    for i, t in enumerate(translations):
        words = re.findall(r"[а-яё\-]+", t.lower())
        if len(words) != 1:
            continue
        w = words[0]
        if w in protected:
            continue
        if w not in _SUBSUMED_AUX_TOKENS:
            continue
        for j, other in enumerate(lower_phrases):
            if i == j or len(other) <= len(t):
                continue
            if re.search(rf"(?<![а-яё]){re.escape(w)}(?![а-яё])", other):
                if len(re.findall(r"[а-яё\-]+", other)) > 1:
                    drop.add(i)
                    break
    return [t for i, t in enumerate(translations) if i not in drop]


def _drop_subsumed_word_fragments(translations, gloss_senses=None):
    """
    Drop lone «печали» if «быть в печали» exists; also multi-word parallel
    tails («до сердца» if «доходить до сердца» exists). Respect gloss-protected.
    """
    if not translations:
        return translations
    protected = _gloss_protected_lemmas(gloss_senses)
    lower_phrases = [t.lower() for t in translations]
    drop = set()
    for i, t in enumerate(translations):
        tl = t.lower().strip()
        words = re.findall(r"[а-яё\-]+", tl)
        if not words:
            continue
        if len(words) == 1 and words[0] in protected:
            continue
        if len(words) > 1 and tl in protected:
            continue
        for j, other in enumerate(lower_phrases):
            if i == j or len(other) <= len(tl):
                continue
            other_words = re.findall(r"[а-яё\-]+", other)
            if len(other_words) <= len(words):
                continue
            if len(words) == 1:
                w = words[0]
                if re.search(rf"(?<![а-яё\-]){re.escape(w)}(?![а-яё\-])", other):
                    drop.add(i)
                    break
            elif other.endswith(" " + tl) or other.endswith(tl):
                # «доходить до сердца» ⊃ «до сердца»
                drop.add(i)
                break
    return [t for i, t in enumerate(translations) if i not in drop]


_NAPRIMER_RE = re.compile(r"(?:^|[^\w])(?:например|напр\.?)(?:[^\w]|$)", re.I)


def _drop_naprimer_index_lines(translations):
    """Drop mangled «… например … сома» expansions — not dictionary index lines."""
    return [t for t in translations if not _NAPRIMER_RE.search(t or "")]


def _repair_orphans_from_original(
    translations, original_translations, gloss_senses=None
):
    """
    If LLM left bare «деготь» after dropping «гнать деготь», restore originals
    that contain the orphan token as a multi-word phrase, then drop the orphan.
    """
    if not translations or not original_translations:
        return translations
    protected = _gloss_protected_lemmas(gloss_senses)
    lowers = [t.lower() for t in translations]
    out = list(translations)
    existing = {t.lower() for t in out}

    original_singles = set()
    for orig in original_translations:
        if not isinstance(orig, str):
            continue
        ol = _normalize_yo_to_e(re.sub(r"\s+", " ", orig.strip())).lower()
        ow = re.findall(r"[а-яё\-]+", ol)
        if len(ow) == 1:
            original_singles.add(ow[0])

    for t in list(translations):
        words = re.findall(r"[а-яё\-]+", t.lower())
        if len(words) != 1:
            continue
        w = words[0]
        if w in protected:
            continue
        # Bare token that is also its own original index line is not an orphan
        # («и» alongside «да и»).
        if w in original_singles:
            continue
        covered = False
        for other in lowers:
            ow = re.findall(r"[а-яё\-]+", other)
            if len(ow) > 1 and re.search(
                rf"(?<![а-яё\-]){re.escape(w)}(?![а-яё\-])", other
            ):
                covered = True
                break
        if covered:
            continue
        restored_any = False
        for orig in original_translations:
            if not isinstance(orig, str):
                continue
            ol = _normalize_yo_to_e(re.sub(r"\s+", " ", orig.strip()))
            if not ol:
                continue
            ow = re.findall(r"[а-яё\-]+", ol.lower())
            if len(ow) < 2:
                continue
            if not re.search(rf"(?<![а-яё\-]){re.escape(w)}(?![а-яё\-])", ol.lower()):
                continue
            if ol.lower() not in existing:
                out.append(ol)
                existing.add(ol.lower())
                restored_any = True
        if restored_any:
            out = [x for x in out if x.lower() != t.lower()]
            lowers = [x.lower() for x in out]
    return out


def _ensure_gloss_standalone_equivalents(translations, gloss_senses):
    """Re-add single-word gloss equivalents dropped by LLM or post-processing."""
    if not gloss_senses:
        return translations
    existing = {t.lower() for t in translations}
    out = list(translations)
    forms = _gloss_standalone_equivalents(gloss_senses)
    forms.extend(
        f
        for f in gloss_listed_single_word_forms(gloss_senses)
        if f.lower() not in {x.lower() for x in forms}
    )
    for form in forms:
        if form.lower() not in existing:
            out.append(form)
            existing.add(form.lower())
    return out


def _keep_service_word_phrase(text):
    """
    Short service-word index line (≤3 tokens): keep dictionary equivalents,
    drop crossrefs and illustration tails («ну а», «а ну», long phrases).
    """
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s or _is_crossref_text(s):
        return False
    words = re.findall(r"[а-яё]+", s.lower())
    if not words or len(words) > 3:
        return False
    if len(words) == 2 and (words[0] == "ну" or words[1] == "ну"):
        return False
    return True


def _filter_service_word_translations(translations, gloss_senses=None):
    return [t for t in translations if _keep_service_word_phrase(t)]


def _preserve_original_service_equivalents(
    translations, original_translations, gloss_senses=None
):
    """Re-add short index entries the LLM dropped («но», «да и», …)."""
    if not original_translations:
        return translations
    existing = {t.lower() for t in translations}
    out = list(translations)
    for item in original_translations:
        if not isinstance(item, str):
            continue
        s = _normalize_yo_to_e(re.sub(r"\s+", " ", item.strip()))
        if not s or s.lower() in existing:
            continue
        if not _keep_service_word_phrase(s):
            continue
        out.append(s)
        existing.add(s.lower())
    return out


def _drop_non_index_entries(translations):
    """Remove cross-ref strings and similar non-translation junk."""
    return [t for t in translations if not _is_crossref_text(t)]


def _html_body_blocks(html):
    """Blocks with semicolon-separated gloss / illustrations."""
    if not html:
        return []
    blocks = []
    if re.search(r"<li[\s>]", html, re.I):
        for m in re.finditer(r"<li[^>]*>(.*?)</li>", html, re.I | re.S):
            chunk = m.group(1)
            if _is_crossref_only(chunk):
                continue
            blocks.append(chunk)
        return blocks
    rest = re.sub(r"^[\s\S]*?</b>\s*", "", html, count=1, flags=re.I)
    rest = re.sub(
        r"^(?:<i[^>]*>[\s\S]*?</i>\s*)+", "", rest.strip(), count=1, flags=re.I
    )
    if rest:
        blocks.append(rest)
    return blocks


def _russian_tail_from_illustration_segment(part):
    part = TAG_RE.sub(" ", part or "")
    part = re.sub(r"\s+", " ", part).strip()
    if " ~ " in part:
        part = part.split(" ~ ", 1)[1].strip()
    part = re.sub(r"~[^\s;]+", " ", part)
    part = _LATIN_WORD_RE.sub(" ", part)
    part = re.sub(r"\s+", " ", part).strip(" ,.")
    part = re.sub(r"[^а-яё\s\-,\.;:!?()]", " ", part, flags=re.I)
    part = re.sub(r"\s+", " ", part).strip(" ,.")
    part = _strip_leading_pos_label(part)
    part = _strip_grammar_parens(part)
    if not part or not re.search(r"[а-яё]", part, re.I):
        return ""
    return _normalize_yo_to_e(part)


def phraseme_russian_phrases_from_html(html):
    """Russian phrases from ◊ phraseme blocks (for post-LLM sanitize gate)."""
    if not html or "◊" not in html:
        return []
    phrases = []
    seen = set()
    for m in re.finditer(r"◊([\s\S]*?)(?=</li>|$)", html, re.I):
        block = TAG_RE.sub(" ", m.group(1))
        block = re.sub(r"\s+", " ", block).strip()
        for part in block.split(";"):
            part = part.strip()
            if not part:
                continue
            rus = _russian_tail_from_illustration_segment(part)
            if not rus:
                continue
            key = rus.lower()
            if key not in seen:
                seen.add(key)
                phrases.append(rus)
    return phrases


def illustration_russian_tails_from_html(html):
    """
    Russian tails of illustration segments (for post-LLM sanitize gate).

    After the first Karelian example in a block, every following semicolon
    segment is an illustration — including pure-Russian tails.
    """
    tails = []
    seen = set()
    for block in _html_body_blocks(html):
        plain = TAG_RE.sub(" ", block)
        plain = re.sub(r"\s+", " ", plain).strip()
        if "◊" in plain:
            plain = plain.split("◊", 1)[0].strip()
        seen_illustration = False
        for part in plain.split(";"):
            part = part.strip()
            if not part:
                continue
            if not seen_illustration:
                if not _is_illustration_segment(part):
                    continue
                seen_illustration = True
            rus = _russian_tail_from_illustration_segment(part)
            if not rus:
                continue
            key = rus.lower()
            if key not in seen:
                seen.add(key)
                tails.append(rus)
    return tails


def _drop_illustration_lines(translations, article_html):
    """Remove index lines matching illustration tails or ◊ phraseme phrases."""
    if not article_html:
        return translations
    tails = {t.lower() for t in illustration_russian_tails_from_html(article_html)}
    tails.update(t.lower() for t in phraseme_russian_phrases_from_html(article_html))
    expanded = set(tails)
    for tail in tails:
        for piece in re.split(r"[,;]", tail):
            piece = _normalize_yo_to_e(re.sub(r"\s+", " ", piece).strip(" ."))
            if piece and re.search(r"[а-яё]", piece, re.I):
                expanded.add(piece.lower())
    if not expanded:
        return translations
    return [t for t in translations if (t or "").lower() not in expanded]


def parse_cleanup_json(text):
    """Parse LLM response; return translations list or None."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return None
    raw = data.get("translations")
    if raw is None or not isinstance(raw, list):
        return None
    return raw


def _finalize_index_spellings(translations):
    """ё→е, strip dict labels / scope parens, dedupe."""
    out = []
    seen = set()
    for t in translations or []:
        s = _strip_labels_across_commas(t)
        s = _strip_scope_parens(s)
        s = _normalize_yo_to_e(re.sub(r"\s+", " ", (s or "").strip()))
        if not s:
            continue
        if s.count("(") != s.count(")"):
            continue
        if _is_mangled_paren_parallel(s):
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def sanitize_cleaned_translations(
    raw,
    *,
    is_service_word=False,
    gloss_senses=None,
    original_translations=None,
    article_html=None,
):
    """
    Post-LLM: normalize ё→е, trim, drop empties, dedupe.

    Phrase gluing / illustration drops / label strips are the LLM's job;
    unused kwargs kept for call-site compatibility.
    """
    if not isinstance(raw, list):
        return None
    out = []
    seen = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        s = _normalize_yo_to_e(re.sub(r"\s+", " ", item.strip()))
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def diff_translations(before, after):
    """Set diff for human review (case-insensitive keys, preserve casing in lists)."""
    before_l = {s.lower(): s for s in before}
    after_l = {s.lower(): s for s in after}
    removed = [before_l[k] for k in before_l if k not in after_l]
    added = [after_l[k] for k in after_l if k not in before_l]
    return {"removed": removed, "added": added}
