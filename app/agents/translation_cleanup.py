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
# Karelian/Latin tokens in gloss tail (before ~ illustrations).
_LATIN_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ''\-]*")

# Match build_ontology.py — function-word POS tags.
SERVICE_POS_KEYWORDS = ["союз", "частица", "предлог", "послелог", "междомети"]

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
)

_PAREN_RE = re.compile(r"\(([^)]*)\)")

_YO_TO_E = str.maketrans({"ё": "е", "Ё": "Е"})

_POS_PREFIX_RE = re.compile(
    r"^(?:conj(?:uctio)?|particl(?:a)?|interj(?:ectio)?|verbum|adverbium|"
    r"adjectivum|reflexivum|флк\.?)\s+",
    re.I,
)

SYSTEM_PROMPT_CLEAN_TRANSLATIONS = (
    "Ты приводишь в порядок РУССКИЕ ПЕРЕВОДЫ одной словарной статьи для "
    "полнотекстового поиска.\n\n"
    "На вход:\n"
    "- translations — текущий список rus_word (может содержать осколки);\n"
    "- gloss_senses — русские gloss'ы по смыслам из словарной статьи (по одному "
    "на <li>, БЕЗ карельских иллюстраций); одно значение = один элемент или "
    "один <li>;\n"
    "- addendum_gloss_senses — то же из аддендумов (дополнений к статье), "
    "если есть; пустой список, если аддендумов нет;\n"
    "- phraseme_senses — устойчивые русские фразы из блоков ◊ (фразеологизмы);\n"
    "- pos_tags, is_service_word.\n\n"
    "gloss_senses и addendum_gloss_senses — главный ориентир смыслов. "
    "translations — сырой индекс. Итог должен покрывать все значения из обоих "
    "списков gloss, но без мусора.\n\n"
    "Цель: каждый элемент списка — один поисковый эквивалент: словарная форма "
    "(лемма) ИЛИ устойчивая фраза («лёгкий на ход», «доходить до сердца»). "
    "Смыслы НЕ терять; разные значения из gloss_senses и addendum_gloss_senses "
    "НЕ сливать.\n\n"
    "СЛОВАРНАЯ ФОРМА:\n"
    "- однословные: сущ./прил. → им. п.; глагол → инфинитив;\n"
    "- фразы из gloss'а не ломать.\n"
    "- одно значение в разных падежах → одна каноническая строка.\n"
    "- в индексе пиши **е**, не **ё** (как в поисковом запросе на сайте: "
    "«придется», «легкий», не «придётся», «лёгкий»).\n"
    "- **согласование внутри фразы:** прилагательное, местоимение и "
    "существительное в одной строке — один род, число и падеж "
    "(«соленая голова крупного сома», не «крупной сома»; "
    "«обрезать перья лука», не «перья лук»).\n\n"
    "СОБРАТЬ ФРАЗЫ ПО GLOSS (важно):\n"
    "- если в gloss параллельные конструкции («доходить до ума, до сердца»), "
    "а в translations только «доходить до ума» и осколок «до сердца» — "
    "добавь «доходить до сердца»;\n"
    "- если в gloss «вызывать отклик», а в списке есть и «вызывать», и "
    "«вызывать отклик» — оставь только фразу;\n"
    "- если «быть» только внутри «быть схожим» в gloss — не оставляй "
    "отдельное «быть»;\n"
    "- если в gloss один глагол относится к нескольким членам параллели "
    "(«делать более лёгким, менее трудным»), каждая строка индекса — "
    "полная глагольная фраза: «делать более лёгким», «делать менее трудным»; "
    "не оставляй голые сравнительные обороты («менее трудным», «более лёгким») "
    "без глагола, если в gloss они в одной параллели с глаголом;\n"
    "- если в gloss общее начало и хвосты через запятую с «и пр.» "
    "(«лучины для плетения лаптей, корзин и пр.»), каждая строка — "
    "полная фраза с этим началом: «лучины для плетения лаптей», "
    "«лучины для плетения корзин»; НИКОГДА не оставляй осколки "
    "«корзин и пр.», «лаптей» без общей части;\n"
    "- если несколько глаголов в одном gloss («очищать, разравнивать …»), "
    "каждый смысл сохраняй с глаголом в индексе (не теряй «очищать», "
    "«разравнивать», «обрезать», «обрывать»).\n"
    "Можно добавлять строки, которых нет дословно в translations, если они "
    "следуют из gloss_senses или addendum_gloss_senses (склейка параллели), "
    "но НЕ выдумывай новые "
    "смыслы и НЕ бери текст из иллюстраций.\n\n"
    "СВЯЗОЧНЫЕ / ВСПОМОГАТЕЛЬНЫЕ (быть, становиться, стать, вызывать, "
    "оказаться, иметься…):\n"
    "- лемма САМА про этот глагол (olla и т.п.) — оставляй смысловые группы "
    "из gloss_senses;\n"
    "- лемма про другое — убери односложные связки/вспомогательные, если в "
    "gloss они только внутри более длинных переводов или в примерах;\n"
    "- односложный глагол без обязательного дополнения из gloss'а не оставляй "
    "(«вызывать» без «отклик», если gloss только «вызывать отклик»).\n\n"
    "СЛУЖЕБНЫЕ ЛЕММЫ (is_service_word): только словарные эквиваленты леммы "
    "(«и», «а», «но», «да», «да и», «а – а»). НИКОГДА не добавляй примерные "
    "предложения из иллюстраций («ну а …», «а иди куда хочешь», «а ну …») — "
    "даже если они встречаются в статье. Не создавай фраз длиннее 3 слов. "
    "Эквиваленты из входного translations не удаляй (в т.ч. «да и», «но»), "
    "если это словарные формы, а не обрывки примеров.\n\n"
    "ОТСЫЛКИ И ФРАЗЕОЛОГИЗМЫ:\n"
    "- НИКОГДА не включай «см. …», «ср. …» — это не переводы, а указатели "
    "на другие статьи;\n"
    "- phraseme_senses (блок ◊) — включай как отдельные устойчивые фразы "
    "в translations («выйти замуж» и т.п.), если они там перечислены.\n\n"
    "СКОБКИ:\n"
    "- ОСТАВЛЯЙ смысловые уточнения: (о корове), (по вкусу), (детс.) — объект, "
    "способ, область значения;\n"
    "- НЕ включай грамматические метки из gloss: (в функции глагола-связки), "
    "(как вспомогательный глагол…), перфект/модальность и т.п.;\n"
    "- не создавай отдельную строку индекса, если без скобок остаётся только "
    "грамматическая помета; для olla достаточно «быть», «существовать»… без "
    "длинных скобочных пояснений про связку/перфект.\n\n"
    "УБРАТЬ: обрывки («ход», «отклик», «ума» без глагола; «менее трудным» "
    "без «делать», если в gloss «делать …, менее …»), дубли, мусор.\n\n"
    "Отвечай СТРОГО одним JSON без markdown: "
    '{"translations": ["...", ...]}.'
)


def _strip_leading_pos_label(text):
    return _POS_PREFIX_RE.sub("", (text or "").strip()).strip()


def _normalize_yo_to_e(text):
    """Match search query normalization (views.search: ё→е before ILIKE/FTS)."""
    return (text or "").translate(_YO_TO_E)


_GLOSS_LABEL_WORDS = frozenset(
    {
        "impersonale",
        "impers",
        "перен",
        "флк",
        "reflex",
        "reflexivum",
        "conj",
        "particl",
        "interj",
        "verbum",
        "adverbium",
        "adjectivum",
    }
)


def _is_illustration_segment(part):
    """Semicolon segment that is a Karelian example, not dictionary gloss."""
    part = (part or "").strip()
    if not part:
        return True
    # «olla ~ быть в обиде» — gloss, not an example sentence.
    if re.search(r"\s~\s+[а-яё]", part, re.I):
        return False
    latin_words = _LATIN_WORD_RE.findall(part)
    if not latin_words:
        return False
    first = latin_words[0].lower().rstrip(".")
    if first in _GLOSS_LABEL_WORDS:
        return False
    if len(latin_words) >= 2:
        return True
    if part.lower().startswith(latin_words[0].lower()):
        return True
    return False


def _is_crossref_text(text):
    """True if text is only a see/cf pointer (см./ср.), not a translation."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not re.search(r"(?:^|\s)(?:см|ср)\.", t, re.I):
        return False
    words = [w for w in re.findall(r"[а-яё]+", t, re.I) if w.lower() not in ("см", "ср")]
    return len(words) == 0


def _is_crossref_only(html_chunk):
    """Entire <li> is a cross-reference, e.g. <i>см.</i> l'is's'e."""
    t = TAG_RE.sub(" ", html_chunk or "")
    t = re.sub(r"\s+", " ", t).strip()
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
    return part


def _expand_comma_parallel(text):
    """
    «быть в обиде, печали» → «быть в обиде, быть в печали» (ellipsis in gloss).
    """
    parts = [p.strip() for p in (text or "").split(",")]
    if len(parts) < 2:
        return text
    out = []
    prefix = None
    for p in parts:
        if not p:
            continue
        words = re.findall(r"[а-яё\-]+", p.lower())
        if len(words) >= 2:
            prefix = " ".join(re.split(r"\s+", p.strip())[:-1])
            out.append(p)
        elif len(words) == 1 and prefix:
            out.append(f"{prefix} {p}")
        else:
            out.append(p)
            prefix = None
    return ", ".join(out)


def _gloss_segments(text):
    """Keep semicolon-separated gloss fragments; drop illustration tails."""
    parts = [p.strip() for p in text.split(";")]
    kept = []
    for part in parts:
        if not part:
            continue
        if _is_illustration_segment(part):
            continue
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
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
        cleaned = _strip_grammar_parens(cleaned)
        cleaned = _expand_comma_parallel(cleaned)
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
        for pm in re.finditer(r";\s*([а-яё][а-яё\s\-]+?)(?:\s+[A-Za-z]|;|$)", block, re.I):
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
    main_html = article.article_html or ""
    addition_htmls = [
        add.article_html or "" for add in article.additions.all().order_by("id")
    ]
    return {
        "word": article.word,
        "translations": translations,
        "gloss_senses": gloss_senses_from_html(main_html),
        "addendum_gloss_senses": addendum_gloss_senses_for(article),
        "phraseme_senses": _merge_phraseme_senses(main_html, addition_htmls),
        "pos_tags": tags,
        "is_service_word": is_service_word_article(tags),
    }


def build_cleanup_user_prompt(art_input):
    return (
        "Статья:\n"
        + json.dumps(art_input, ensure_ascii=False)
        + "\n\nВерни очищенный список translations."
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
                phrase = _normalize_yo_to_e(re.sub(r"\s+", " ", (prefix + tail).strip()))
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
        for chunk in re.split(r"[;,]", sense):
            chunk = _strip_grammar_parens(chunk.strip())
            chunk = re.sub(r"\s+", " ", chunk).strip()
            if chunk and re.search(r"[а-яё]", chunk, re.I):
                chunks.append(chunk)
        has_multi = any(len(re.findall(r"[а-яё\-]+", c.lower())) >= 2 for c in chunks)
        for chunk in chunks:
            if len(re.findall(r"[а-яё\-]+", chunk.lower())) != 1:
                continue
            if has_multi:
                continue
            key = chunk.lower()
            if key not in seen:
                seen.add(key)
                forms.append(chunk)
    return forms


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
    """Drop lone «печали» if «быть в печали» exists; respect gloss-protected lemmas."""
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
        for j, other in enumerate(lower_phrases):
            if i == j or len(other) <= len(t):
                continue
            if re.search(rf"(?<![а-яё]){re.escape(w)}(?![а-яё])", other):
                if len(re.findall(r"[а-яё\-]+", other)) > 1:
                    drop.add(i)
                    break
    return [t for i, t in enumerate(translations) if i not in drop]


def _ensure_gloss_standalone_equivalents(translations, gloss_senses):
    """Re-add single-word gloss equivalents dropped by LLM or post-processing."""
    if not gloss_senses:
        return translations
    existing = {t.lower() for t in translations}
    out = list(translations)
    for form in _gloss_standalone_equivalents(gloss_senses):
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


def sanitize_cleaned_translations(
    raw, *, is_service_word=False, gloss_senses=None, original_translations=None
):
    """
    Post-LLM: strip, dedupe, drop empties, remove aux tokens subsumed by phrases.
    """
    if not isinstance(raw, list):
        return None
    out = []
    seen = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        s = re.sub(r"\s+", " ", item.strip())
        s = _strip_grammar_parens(s)
        s = _normalize_yo_to_e(s)
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    out = _expand_parallel_verb_fragments(out)
    out = _drop_subsumed_auxiliaries(out, gloss_senses)
    out = _drop_subsumed_word_fragments(out, gloss_senses)
    out = _ensure_gloss_standalone_equivalents(out, gloss_senses)
    out = _ensure_i_pro_parallel_phrases(out, gloss_senses)
    out = _drop_i_pro_tail_fragments(out)
    out = _drop_non_index_entries(out)
    if is_service_word:
        out = _filter_service_word_translations(out, gloss_senses)
        out = _preserve_original_service_equivalents(
            out, original_translations, gloss_senses
        )
    return out


def diff_translations(before, after):
    """Set diff for human review (case-insensitive keys, preserve casing in lists)."""
    before_l = {s.lower(): s for s in before}
    after_l = {s.lower(): s for s in after}
    removed = [before_l[k] for k in before_l if k not in after_l]
    added = [after_l[k] for k in after_l if k not in before_l]
    return {"removed": removed, "added": added}
