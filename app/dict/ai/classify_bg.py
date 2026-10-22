"""
Background scheduling for single-article ontology classification.

Uses a daemon thread (no Celery/RQ in this project). Callers must not invoke
classify from Article.save() — translations inlines are written later
(see docs/method-onthlogy-markup.md §5). Prefer response_add / an admin POST
after save_related.

Completion notices are kept in-process (same worker as the thread) and flushed
into django.contrib.messages on the next /admin/ request (see middleware).
"""

from __future__ import annotations

import logging
import threading

from dict.models import Article, ArticleKeyword

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_inflight: set[int] = set()

_notices_lock = threading.Lock()
# user_id -> list of notice dicts (ok, article_id, word, fields, error, …)
_pending_notices: dict[int, list[dict]] = {}


def article_has_ontology_markup(article) -> bool:
    """True if the article has fields and/or keywords (incl. no_field + keywords)."""
    if article.semantic_assignments.exists():
        return True
    return ArticleKeyword.objects.filter(article_id=article.pk).exists()


def is_classify_inflight(article_id: int) -> bool:
    with _lock:
        return article_id in _inflight


def push_classify_notice(user_id: int | None, notice: dict) -> None:
    """Queue a notice for the next admin page load of this user."""
    if user_id is None:
        return
    uid = int(user_id)
    with _notices_lock:
        _pending_notices.setdefault(uid, []).append(notice)


def pop_classify_notices(user_id: int) -> list[dict]:
    """Take and clear all pending notices for user_id."""
    uid = int(user_id)
    with _notices_lock:
        return _pending_notices.pop(uid, [])


def format_classify_notice_message(notice: dict) -> str:
    """Human-readable admin alert text."""
    word = notice.get("word") or f"#{notice.get('article_id')}"
    if notice.get("ok"):
        fields = notice.get("fields") or []
        if fields:
            joined = ", ".join(fields)
            return f"Онтология: «{word}» — размечено ({joined})."
        if notice.get("no_field"):
            return f"Онтология: «{word}» — без смыслового поля (no_field)."
        return f"Онтология: «{word}» — разметка завершена (полей нет)."
    err = notice.get("error") or "ошибка"
    return f"Онтология: «{word}» — не удалось ({err})."


def schedule_classify_article(article_id: int, *, user_id: int | None = None) -> bool:
    """
    Start classify_article in a daemon thread.

    Returns False if this article_id is already running (caller may warn).
    On success returns True immediately; LLM work continues in the background.
    When finished, pushes an admin notice for user_id (if given).
    """
    article_id = int(article_id)
    try:
        word = Article.objects.values_list("word", flat=True).get(pk=article_id)
    except Article.DoesNotExist:
        word = f"#{article_id}"

    with _lock:
        if article_id in _inflight:
            return False
        _inflight.add(article_id)

    def runner():
        from django.db import close_old_connections

        from dict.ai.classify import classify_article

        notice = {
            "article_id": article_id,
            "word": word,
            "ok": False,
            "fields": [],
            "no_field": False,
            "error": "crashed",
        }
        try:
            close_old_connections()
            result = classify_article(article_id)
            notice["ok"] = bool(result.get("ok"))
            notice["fields"] = list(result.get("fields") or [])
            notice["no_field"] = bool(result.get("no_field"))
            notice["error"] = result.get("error") or ("" if notice["ok"] else "unknown")
            if not notice["ok"]:
                logger.warning(
                    "Background classify article %s failed: %s",
                    article_id,
                    notice["error"],
                )
        except Exception:
            logger.exception("Background classify article %s crashed", article_id)
            notice["ok"] = False
            notice["error"] = "crashed"
        finally:
            push_classify_notice(user_id, notice)
            close_old_connections()
            with _lock:
                _inflight.discard(article_id)

    threading.Thread(
        target=runner,
        name=f"classify-article-{article_id}",
        daemon=True,
    ).start()
    return True
