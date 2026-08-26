"""
Classify one dictionary article against the frozen ontology in the DB.

Uses the Timeweb gateway (TIMEWEB_AI_MODEL_CLASSIFY = DeepSeek), not the
offline DeepSeek key in agents/.env. Designed to be called from a management
command now and from a background worker later: no request object, no HTTP.

Does not raise on LLM failure — returns ok=False so the caller can log and
move on. Persistence is per-article only; other articles are left untouched.
"""

from django.conf import settings
from django.db import transaction

from dict.ai import client as ai_client
from dict.ai.prompts import (
    SYSTEM_PROMPT_FROZEN,
    build_article_input,
    build_user_prompt,
    ontology_from_db,
)
from dict.models import (
    Article,
    ArticleKeyword,
    ArticleSemanticField,
    SemanticField,
)

CLASSIFY_TIMEOUT = 45


def sanitize_keyword(word):
    """Same sanitation as load_keywords: strip, lower, drop short/numeric."""
    w = (word or "").strip().lower()
    if len(w) < 2:
        return None
    if w.isdigit():
        return None
    return w


def _empty_result(article_id, error, persist):
    return {
        "ok": False,
        "article_id": article_id,
        "fields": [],
        "keywords": [],
        "no_field": False,
        "error": error,
        "persisted": False,
        "dry_run": not persist,
    }


def classify_article(article_id, persist=True, timeout=CLASSIFY_TIMEOUT):
    """
    Classify a single article by id.

    Returns a dict with ok, article_id, fields, keywords, no_field, error,
    persisted, dry_run. persist=False only runs the model (for --dry-run).

    Background callers should close_old_connections() themselves around
    this function — it must not close the connection used by tests or
    management commands.
    """
    try:
        article = Article.objects.get(pk=article_id)
    except Article.DoesNotExist:
        return _empty_result(article_id, "not_found", persist)

    field_defs = ontology_from_db()
    if not field_defs:
        return _empty_result(article_id, "empty_ontology", persist)

    model = getattr(settings, "TIMEWEB_AI_MODEL_CLASSIFY", "")
    data = ai_client.chat_json(
        SYSTEM_PROMPT_FROZEN,
        build_user_prompt(build_article_input(article), field_defs),
        model,
        timeout=timeout,
    )
    if data is None:
        return _empty_result(article_id, "llm_unavailable", persist)

    raw_fields = data.get("fields") or []
    if not isinstance(raw_fields, list):
        raw_fields = []
    fields = []
    for name in raw_fields:
        if name in field_defs and name not in fields:
            fields.append(name)

    raw_kw = data.get("keywords") or []
    if not isinstance(raw_kw, list):
        raw_kw = []
    keywords = []
    seen = set()
    for raw in raw_kw:
        w = sanitize_keyword(raw if isinstance(raw, str) else str(raw))
        if not w or w in seen:
            continue
        seen.add(w)
        keywords.append(w)

    no_field = bool(data.get("no_field"))
    result = {
        "ok": True,
        "article_id": article.id,
        "fields": fields,
        "keywords": keywords,
        "no_field": no_field,
        "error": None,
        "persisted": False,
        "dry_run": not persist,
    }
    if persist:
        _persist(article.id, fields, keywords)
        result["persisted"] = True
    return result


def _persist(article_id, fields, keywords):
    field_id_by_name = dict(SemanticField.objects.values_list("name", "id"))
    with transaction.atomic():
        ArticleSemanticField.objects.filter(article_id=article_id).delete()
        ArticleKeyword.objects.filter(article_id=article_id).delete()
        ArticleSemanticField.objects.bulk_create(
            [
                ArticleSemanticField(
                    article_id=article_id, field_id=field_id_by_name[name]
                )
                for name in fields
                if name in field_id_by_name
            ]
        )
        ArticleKeyword.objects.bulk_create(
            [ArticleKeyword(article_id=article_id, word=w) for w in keywords]
        )
