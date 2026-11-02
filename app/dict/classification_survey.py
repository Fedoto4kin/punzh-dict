"""
Visitor classification survey (control channel).

Eligible articles: POS in {s, v, a, adv}, own translations, non-empty HTML body.
"""

from __future__ import annotations

import random
import re
from typing import Iterable
from urllib.parse import quote

from django.conf import settings
from django.db.models import Count, Prefetch, Q
from django.utils.html import strip_tags

from dict.ai.prompts import build_article_input
from dict.helpers import normalization
from dict.models import (
    Article,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ClassificationSurveyResponse,
    SemanticField,
)

CONTENT_POS_TAGS = ("s", "v", "a", "adv")
TASK_SIZE = 3
MAX_FIELDS_PER_ARTICLE = 3

# Homonym index after lemma: «dara II», «mado 2» (same idea as see_audit).
_HOMONYM_TAIL = re.compile(r"(?:\s+(?:\d+|[IVXivx]{1,5}))+$")


def survey_enabled() -> bool:
    return bool(getattr(settings, "CLASSIFICATION_SURVEY", False))


def field_catalog() -> list[dict]:
    return [
        {"name": f.name, "definition": f.definition or ""}
        for f in SemanticField.objects.order_by("sorting", "name")
    ]


def _has_nonempty_body(html: str) -> bool:
    text = strip_tags(html or "").strip()
    return len(text) >= 8


def eligible_article_qs():
    """Articles with content POS, translation, and non-empty body."""
    return (
        Article.objects.filter(
            articleindextag__tag__tag__in=CONTENT_POS_TAGS,
            articleindextranslate__rus_word__isnull=False,
        )
        .exclude(articleindextranslate__rus_word="")
        .exclude(Q(article_html__isnull=True) | Q(article_html__exact=""))
        .distinct()
    )


def eligible_article_ids(exclude_ids: Iterable[int] | None = None) -> list[int]:
    exclude = set(exclude_ids or ())
    qs = eligible_article_qs()
    if exclude:
        qs = qs.exclude(id__in=exclude)
    # Filter empty body in Python only for candidates we might pick is expensive
    # on full corpus; do a cheap HTML length filter in SQL first, then verify.
    ids = list(
        qs.exclude(article_html__regex=r"^\s*$").values_list("id", flat=True)[:5000]
    )
    if not ids:
        return []
    # Spot-check bodies for a shuffled subset large enough to build a task.
    random.shuffle(ids)
    good = []
    html_by_id = dict(
        Article.objects.filter(id__in=ids[:800]).values_list("id", "article_html")
    )
    for aid in ids:
        html = html_by_id.get(aid)
        if html is None:
            continue
        if _has_nonempty_body(html):
            good.append(aid)
        if len(good) >= 200:
            break
    return good


def _pos_tags_for_articles(article_ids: list[int]) -> dict[int, set[str]]:
    rows = ArticleIndexTag.objects.filter(
        article_id__in=article_ids, tag__tag__in=CONTENT_POS_TAGS
    ).values_list("article_id", "tag__tag")
    out: dict[int, set[str]] = {}
    for aid, tag in rows:
        out.setdefault(aid, set()).add(tag)
    return out


def pick_task_article_ids(
    respondent_key: str, n: int = TASK_SIZE, rng: random.Random | None = None
) -> list[int]:
    """Pick up to n eligible articles not yet answered by this respondent."""
    rng = rng or random.Random()
    answered = set(
        ClassificationSurveyResponse.objects.filter(
            respondent_key=respondent_key
        ).values_list("article_id", flat=True)
    )
    pool = eligible_article_ids(exclude_ids=answered)
    if not pool:
        return []
    rng.shuffle(pool)
    pos_map = _pos_tags_for_articles(pool[:150])
    picked: list[int] = []
    used_pos: set[str] = set()

    # Prefer POS diversity (s / v / a / adv) across the three cards.
    for aid in pool:
        if len(picked) >= n:
            break
        tags = pos_map.get(aid) or set()
        if tags and tags.isdisjoint(used_pos):
            picked.append(aid)
            used_pos |= tags

    for aid in pool:
        if len(picked) >= n:
            break
        if aid not in picked:
            picked.append(aid)
    return picked[:n]


def article_display_word(article: Article) -> str:
    """Same surface form as public word cards (приведённая орфография)."""
    corrected = (article.word_normalized or "").strip()
    if corrected:
        return corrected
    return normalization(article.word)


def article_search_query(display: str) -> str:
    """Lemma for /search/: first variant, without trailing homonym number."""
    w = (display or "").split(",", 1)[0].strip()
    return _HOMONYM_TAIL.sub("", w).strip()


def article_payload(article: Article) -> dict:
    inp = build_article_input(article)
    pos = [
        t.tag.tag
        for t in article.articleindextag_set.all()
        if t.tag.tag in CONTENT_POS_TAGS
    ]
    display = article_display_word(article)
    query = article_search_query(display) or display
    return {
        "article_id": article.id,
        "word": display,
        "word_original": article.word,
        # Visible lemma may keep «II»; search index uses the bare word.
        "url": "/search/" + quote(query, safe=""),
        "translations": inp["translations"],
        "illustrations_ru": inp["illustrations_ru"],
        "pos": pos,
    }


def build_task_payload(respondent_key: str) -> dict:
    ids = pick_task_article_ids(respondent_key)
    qs = (
        Article.objects.filter(id__in=ids)
        .prefetch_related(
            "articleindextranslate_set",
            "additions",
            Prefetch(
                "articleindextag_set",
                queryset=ArticleIndexTag.objects.select_related("tag"),
            ),
        )
        .order_by("id")
    )
    by_id = {a.id: a for a in qs}
    articles = [article_payload(by_id[i]) for i in ids if i in by_id]
    return {
        "articles": articles,
        "fields": field_catalog(),
        "task_size": TASK_SIZE,
        "max_fields": MAX_FIELDS_PER_ARTICLE,
    }


def validate_and_store_answers(respondent_key: str, answers: list[dict]) -> int:
    """
    Persist answers. Returns number stored.
    Each answer: {article_id, decision, fields: [str, ...]}.
    """
    if not respondent_key or not isinstance(answers, list):
        raise ValueError("bad payload")
    if not (1 <= len(answers) <= TASK_SIZE):
        raise ValueError("expected 1–3 answers")

    known_fields = set(SemanticField.objects.values_list("name", flat=True))
    allowed_decision = {
        ClassificationSurveyResponse.DECISION_FIELDS,
        ClassificationSurveyResponse.DECISION_NO_FIELD,
        ClassificationSurveyResponse.DECISION_INSUFFICIENT,
    }
    stored = 0
    for raw in answers:
        aid = int(raw["article_id"])
        decision = (raw.get("decision") or "").strip()
        if decision not in allowed_decision:
            raise ValueError(f"bad decision for {aid}")
        fields = raw.get("fields") or []
        if not isinstance(fields, list):
            raise ValueError(f"bad fields for {aid}")
        fields = [str(f).strip() for f in fields if str(f).strip()]
        if len(fields) > MAX_FIELDS_PER_ARTICLE:
            raise ValueError(f"too many fields for {aid}")
        for name in fields:
            if name not in known_fields:
                raise ValueError(f"unknown field {name!r}")
        if decision == ClassificationSurveyResponse.DECISION_FIELDS:
            if not fields:
                raise ValueError(f"fields required for {aid}")
        else:
            fields = []
        if not Article.objects.filter(id=aid).exists():
            raise ValueError(f"unknown article {aid}")
        ClassificationSurveyResponse.objects.update_or_create(
            respondent_key=respondent_key,
            article_id=aid,
            defaults={"decision": decision, "fields": fields},
        )
        stored += 1
    return stored


def pool_stats() -> dict:
    """Lightweight counts for admin / sanity checks."""
    base = eligible_article_qs().count()
    return {
        "eligible_qs_approx": base,
        "responses": ClassificationSurveyResponse.objects.count(),
        "respondents": ClassificationSurveyResponse.objects.values("respondent_key")
        .annotate(n=Count("id"))
        .count(),
    }
