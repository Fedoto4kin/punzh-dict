"""
Classify one dictionary article against the frozen ontology in the DB.

Uses the Timeweb gateway (TIMEWEB_AI_MODEL_CLASSIFY = DeepSeek), not the
offline DeepSeek key in agents/.env. Designed to be called from a management
command now and from a background worker later: no request object, no HTTP.

Does not raise on LLM failure — returns ok=False so the caller can log and
move on. Persistence is per-article only; other articles are left untouched.
"""

import logging

from django.conf import settings
from django.db import transaction

from dict.ai import client as ai_client
from dict.ai.prompts import (
    SYSTEM_PROMPT_FROZEN,
    SYSTEM_PROMPT_TRANSLATION_FIELDS,
    build_article_input,
    build_translation_fields_user_prompt,
    build_user_prompt,
    ontology_from_db,
    parse_translation_fields,
    translations_for_classification,
)
from dict.models import (
    Article,
    ArticleKeyword,
    ArticleSemanticField,
    SemanticField,
)

logger = logging.getLogger(__name__)

CLASSIFY_TIMEOUT = 45

ARTICLE_PREFETCH = (
    "additions",
    "articleindextranslate_set",
    "semantic_assignments__field",
)


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
        "translation_fields": [],
        "keywords": [],
        "no_field": False,
        "error": error,
        "persisted": False,
        "dry_run": not persist,
    }


def _pick_translation_fields(article, fields, field_defs, model, timeout):
    """Second LLM call: which assigned fields follow from the translation index."""
    if not fields:
        return []
    translations = translations_for_classification(article)
    data = ai_client.chat_json(
        SYSTEM_PROMPT_TRANSLATION_FIELDS,
        build_translation_fields_user_prompt(translations, fields, field_defs),
        model,
        timeout=timeout,
    )
    if data is None:
        return None
    return parse_translation_fields(data, fields)


def classify_article(article_id, persist=True, timeout=CLASSIFY_TIMEOUT):
    """
    Classify a single article by id.

    Returns a dict with ok, article_id, fields, translation_fields, keywords,
    no_field, error, persisted, dry_run. persist=False only runs the model
    (for --dry-run).

    Background callers should close_old_connections() themselves around
    this function — it must not close the connection used by tests or
    management commands.
    """
    try:
        article = Article.objects.prefetch_related(*ARTICLE_PREFETCH).get(pk=article_id)
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
    translation_fields = []
    translation_fields_error = None
    if fields:
        picked = _pick_translation_fields(article, fields, field_defs, model, timeout)
        if picked is None:
            translation_fields_error = "translation_fields_unavailable"
            logger.warning(
                "Article %s: translation_fields LLM failed; "
                "from_translation will be False for all fields.",
                article_id,
            )
        else:
            translation_fields = picked

    result = {
        "ok": True,
        "article_id": article.id,
        "fields": fields,
        "translation_fields": translation_fields,
        "keywords": keywords,
        "no_field": no_field,
        "error": translation_fields_error,
        "persisted": False,
        "dry_run": not persist,
    }
    if persist:
        _persist(article.id, fields, keywords, translation_fields)
        result["persisted"] = True
    return result


def _persist(article_id, fields, keywords, translation_fields=None):
    translation_set = set(translation_fields or [])
    field_id_by_name = dict(SemanticField.objects.values_list("name", "id"))
    with transaction.atomic():
        ArticleSemanticField.objects.filter(article_id=article_id).delete()
        ArticleKeyword.objects.filter(article_id=article_id).delete()
        ArticleSemanticField.objects.bulk_create(
            [
                ArticleSemanticField(
                    article_id=article_id,
                    field_id=field_id_by_name[name],
                    from_translation=(name in translation_set),
                )
                for name in fields
                if name in field_id_by_name
            ]
        )
        ArticleKeyword.objects.bulk_create(
            [ArticleKeyword(article_id=article_id, word=w) for w in keywords]
        )
