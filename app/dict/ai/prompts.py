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
    "иллюстраций.\n"
    "СТРОГО: относи ТОЛЬКО к полям из данного списка. НОВЫЕ поля заводить "
    "ЗАПРЕЩЕНО. Если статья не подходит ни к одному полю (служебное слово, "
    'частица, союз) — верни пустой список полей и "no_field": true. '
    "Ставь 1-3 наиболее релевантных поля, не больше.\n"
    "Отвечай СТРОГО одним JSON без markdown: "
    '{"keywords": [..], "fields": [..], "no_field": false}.'
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


def build_article_input(article):
    """
    Russian-only payload for one article: translations plus Cyrillic from
    HTML (illustrations), minus strings already present as translations.
    Matches the mass-labeling input, including the Karelian headword key.
    """
    translations = list(
        ArticleIndexTranslate.objects.filter(article=article)
        .exclude(rus_word__isnull=True)
        .values_list("rus_word", flat=True)
    )
    cyr = cyrillic_from_html(article.article_html)
    tr_set = set(t.lower() for t in translations if t)
    illustr = [c for c in cyr if c.lower() not in tr_set]
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


def ontology_from_db():
    """Frozen ontology as name -> definition, from SemanticField."""
    return dict(SemanticField.objects.values_list("name", "definition"))
