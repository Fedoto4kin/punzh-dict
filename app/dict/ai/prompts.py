"""
Shared prompt and article input for frozen-ontology classification.

Same text and input shape as the mass pass in agents/build_ontology.py
(SYSTEM_PROMPT_FROZEN). Runtime classify and the offline script both import
from here so the two paths cannot drift.
"""

import json
import re

from dict.models import ArticleIndexTranslate, SemanticField

TAG_RE = re.compile(r"<[^>]+>")
CYR_RE = re.compile(r"[а-яёА-ЯЁ][а-яёА-ЯЁ \-,;]*[а-яёА-ЯЁ]")

SYSTEM_PROMPT_FROZEN = (
    "Ты классифицируешь словарную статью по ФИКСИРОВАННОМУ списку смысловых "
    "полей. На вход — РУССКИЕ данные статьи: переводы и русские фрагменты "
    "иллюстраций (включая аддендумы — дополнения к статье, если есть).\n"
    "СТРОГО: относи ТОЛЬКО к полям из данного списка. НОВЫЕ поля заводить "
    "ЗАПРЕЩЕНО. Если статья не подходит ни к одному полю (служебное слово, "
    'частица, союз) — верни пустой список полей и "no_field": true. '
    "Ставь 1-3 наиболее релевантных поля, не больше.\n"
    "Отвечай СТРОГО одним JSON без markdown: "
    '{"keywords": [..], "fields": [..], "no_field": false}.'
)

SYSTEM_PROMPT_TRANSLATION_FIELDS = (
    "Ты смотришь смысловые поля словарной статьи и решаешь, какие из них "
    "относятся к ПЕРЕВОДАМ леммы, а какие нет. "
    "На вход — РУССКИЕ ПЕРЕВОДЫ леммы "
    "и закрытый список уже проставленных смысловых полей (имя и определение). "
    "Иллюстрации и примеры употребления тебе НЕ даны и учитывать их НЕЛЬЗЯ.\n"
    "Поле «по переводу» — его смысл виден в переводах леммы. "
    "Поле только из примера / соседний смысл, которого нет в переводах, "
    "в список НЕ включай. Можно отметить НЕСКОЛЬКО полей (многозначность) "
    "или НИ ОДНОГО, если ни одно поле не следует из переводов "
    "(пустые/мусорные переводы, поля не про лемму).\n"
    "Отвечай СТРОГО одним JSON без markdown, имена СТРОГО из списка: "
    '{"translation_fields": ["имя", ...]}.'
)


def cyrillic_from_html(html):
    """Russian spans from HTML (glosses mixed with illustration tails)."""
    if not html:
        return []
    text = TAG_RE.sub(" ", html)
    out = []
    for c in CYR_RE.findall(text):
        c = re.sub(r"\s+", " ", c).strip()
        if len(c) > 2:
            out.append(c)
    return out


def article_html_blobs(article):
    """Main article HTML plus ArticleAddition blocks, in id order."""
    blobs = [article.article_html or ""]
    for add in article.additions.all().order_by("id"):
        blobs.append(add.article_html or "")
    return blobs


def indexed_translations(article):
    """rus_word values from ArticleIndexTranslate (prefetch-friendly)."""
    if (
        hasattr(article, "_prefetched_objects_cache")
        and "articleindextranslate_set" in article._prefetched_objects_cache
    ):
        rows = article.articleindextranslate_set.all()
    else:
        rows = ArticleIndexTranslate.objects.filter(article=article)
    return [t.rus_word for t in rows if t.rus_word]


def translations_for_classification(article):
    """
    Translation strings for the «from translation» pass.

    Only ArticleIndexTranslate.rus_word (addendum senses are already
    stored there). Do not parse HTML.
    """
    return indexed_translations(article)


def build_article_input(article):
    """
    Russian-only payload for one article: translations plus Cyrillic from
    HTML (illustrations), minus strings already present as translations.
    Includes ArticleAddition blocks. Matches the mass-labeling input shape.
    """
    translations = indexed_translations(article)
    cyr = []
    for blob in article_html_blobs(article):
        cyr.extend(cyrillic_from_html(blob))
    tr_set = set(t.lower() for t in translations if t)
    illustr = []
    seen_ill = set()
    for c in cyr:
        if c.lower() in tr_set or c.lower() in seen_ill:
            continue
        seen_ill.add(c.lower())
        illustr.append(c)
    return {
        "word": article.word,
        "translations": translations,
        "illustrations_ru": illustr[:15],
    }


def build_user_prompt(art_input, field_defs):
    cats = [{"field": f, "definition": d} for f, d in sorted(field_defs.items())]
    return (
        "Смысловые поля (классифицируй строго по ним):\n"
        + json.dumps(cats, ensure_ascii=False)
        + "\n\nСтатья:\n"
        + json.dumps(art_input, ensure_ascii=False)
    )


def field_defs_for_names(field_defs, names):
    """Subset of ontology entries for the given field names (deduped)."""
    payload = []
    seen = set()
    for name in names:
        if name in seen or name not in field_defs:
            continue
        seen.add(name)
        payload.append({"field": name, "definition": field_defs[name] or ""})
    return payload


def build_translation_fields_user_prompt(translations, field_names, field_defs):
    fields = field_defs_for_names(field_defs, field_names)
    return "Переводы леммы:\n" + json.dumps(
        translations, ensure_ascii=False
    ) + "\n\nУже проставленные смысловые поля " "(верни те, что следуют из переводов):\n" + json.dumps(
        fields, ensure_ascii=False
    )


def parse_translation_fields(data, allowed_names):
    """Parse translation_fields from LLM JSON; names must be in allowed_names."""
    if not data:
        return None
    raw = data.get("translation_fields")
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    allowed = set(allowed_names)
    chosen = []
    for name in raw:
        if name in allowed and name not in chosen:
            chosen.append(name)
    return chosen


def ontology_from_db():
    """Frozen ontology as name -> definition, from SemanticField."""
    return dict(SemanticField.objects.values_list("name", "definition"))
