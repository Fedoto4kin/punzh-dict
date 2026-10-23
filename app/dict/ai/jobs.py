"""
Background runner for AiSearchJob (thread per job, state in Postgres).

Pattern mirrors classify_bg: enable-threads=true on uwsgi; no Celery/Redis.
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

from django.utils import timezone

from dict.models import AiSearchJob

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_inflight: set[str] = set()

STALE_RUNNING_SECONDS = 90
JOB_TTL_HOURS = 24
RATE_LIMIT_PER_MINUTE = 20
MAX_QUERY_LEN = 300


def serialize_groups_for_job(groups):
    """Light JSON: no Article HTML — ids + titles for later hydrate/partial."""
    out = []
    for g in groups or []:
        item = {
            "kind": g.get("kind"),
            "title": g.get("title"),
            "total": g.get("total"),
            "more": g.get("more", 0),
            "articles": [
                {"id": a.get("id"), "word": a.get("word")}
                for a in (g.get("articles") or [])
                if isinstance(a, dict) and a.get("id") is not None
            ],
        }
        if g.get("fields"):
            item["fields"] = g["fields"]
        if g.get("demote_ids"):
            item["demote_ids"] = list(g["demote_ids"])
        out.append(item)
    return out


def serialize_parsed_for_job(parsed):
    """Drop raw LLM blob / meta noise; keep axes for UI."""
    if not parsed:
        return None
    keys = (
        "ok",
        "parse_ok",
        "query",
        "lexical",
        "focus",
        "related",
        "fields",
        "tags",
        "tags_soft",
        "tags_display",
        "tags_soft_display",
        "place",
        "place_display",
        "dialect",
        "dialect_display",
        "dropped",
        "display",
        "krl_headword",
        "warnings",
        "error",
    )
    return {k: parsed.get(k) for k in keys if k in parsed}


def mark_stale_running(job):
    """If stuck in running/ranking too long → error. Returns True if marked."""
    if job.status not in (
        AiSearchJob.STATUS_RUNNING,
        AiSearchJob.STATUS_RANKING,
    ):
        return False
    age = timezone.now() - (job.updated_at or job.created_at)
    if age < timedelta(seconds=STALE_RUNNING_SECONDS):
        return False
    job.status = AiSearchJob.STATUS_ERROR
    job.error = "timeout_or_stale"
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error", "finished_at", "updated_at"])
    return True


def expire_old_jobs(older_than_hours=JOB_TTL_HOURS):
    """Mark old jobs expired (cheap GC)."""
    cutoff = timezone.now() - timedelta(hours=older_than_hours)
    return (
        AiSearchJob.objects.filter(
            created_at__lt=cutoff,
            status__in=(
                AiSearchJob.STATUS_QUEUED,
                AiSearchJob.STATUS_DONE,
                AiSearchJob.STATUS_ERROR,
            ),
        )
        .exclude(status=AiSearchJob.STATUS_EXPIRED)
        .update(status=AiSearchJob.STATUS_EXPIRED)
    )


def rate_limit_ok(client_key):
    if not client_key:
        return True
    since = timezone.now() - timedelta(minutes=1)
    n = AiSearchJob.objects.filter(client_key=client_key, created_at__gte=since).count()
    return n < RATE_LIMIT_PER_MINUTE


def create_job(query, *, sort="relevance", client_key=""):
    q = (query or "").strip()[:MAX_QUERY_LEN]
    job = AiSearchJob.objects.create(
        query=q,
        sort=(sort or "relevance")[:16],
        client_key=(client_key or "")[:64],
        status=AiSearchJob.STATUS_QUEUED,
    )
    schedule_ai_search_job(str(job.id))
    return job


def schedule_ai_search_job(job_id: str) -> bool:
    """Start run_job in a daemon thread. False if already inflight here."""
    jid = str(job_id)
    with _lock:
        if jid in _inflight:
            return False
        _inflight.add(jid)

    def runner():
        from django.db import close_old_connections

        try:
            close_old_connections()
            run_job(jid)
        except Exception:
            logger.exception("ai search job %s crashed", jid)
            try:
                close_old_connections()
                AiSearchJob.objects.filter(pk=jid).update(
                    status=AiSearchJob.STATUS_ERROR,
                    error="worker_crash",
                    finished_at=timezone.now(),
                )
            except Exception:
                logger.exception("failed to mark job %s error", jid)
        finally:
            close_old_connections()
            with _lock:
                _inflight.discard(jid)

    threading.Thread(target=runner, daemon=True, name=f"ai-search-{jid[:8]}").start()
    return True


def run_job(job_id: str):
    """parse_query + search_by_parsed (+ optional LLM re-rank) → persist JSON."""
    from dict.ai.query_parse import parse_query
    from dict.ai.rank import SORT_RELEVANCE, normalize_sort
    from dict.ai.rerank import apply_rerank_to_groups, rerank_enabled
    from dict.ai.search import search_by_parsed

    try:
        job = AiSearchJob.objects.get(pk=job_id)
    except AiSearchJob.DoesNotExist:
        return

    if job.status in (
        AiSearchJob.STATUS_DONE,
        AiSearchJob.STATUS_ERROR,
        AiSearchJob.STATUS_EXPIRED,
    ):
        return

    job.status = AiSearchJob.STATUS_RUNNING
    job.save(update_fields=["status", "updated_at"])

    try:
        parsed = parse_query(job.query)
        sort = normalize_sort(job.sort)
        groups, fallback_count = search_by_parsed(parsed, sort=sort)
        job.parsed = serialize_parsed_for_job(parsed)
        job.fallback_count = fallback_count

        if (
            sort == SORT_RELEVANCE
            and rerank_enabled()
            and groups
            and fallback_count is None
        ):
            job.status = AiSearchJob.STATUS_RANKING
            job.save(update_fields=["parsed", "fallback_count", "status", "updated_at"])
            groups = apply_rerank_to_groups(job.query, groups, sort=sort)

        job.groups = serialize_groups_for_job(groups)
        job.status = AiSearchJob.STATUS_DONE
        job.error = ""
        job.finished_at = timezone.now()
        job.save(
            update_fields=[
                "parsed",
                "groups",
                "fallback_count",
                "status",
                "error",
                "finished_at",
                "updated_at",
            ]
        )
    except Exception as exc:
        logger.exception("ai search job %s failed", job_id)
        job.status = AiSearchJob.STATUS_ERROR
        job.error = (str(exc) or "error")[:200]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at", "updated_at"])


def hydrate_job_groups(job, sort=None):
    """
    Rebuild template-ready groups from a done job.

    If sort differs from the job's stored sort, re-run search_by_parsed on the
    saved parse (SQL only — no LLM) so alphabet/relevance can switch cheaply.
    """
    from dict.ai.rank import normalize_sort
    from dict.ai.search import hydrate_group_articles, search_by_parsed

    want = normalize_sort(sort if sort is not None else job.sort)
    stored = normalize_sort(job.sort)
    parsed = job.parsed or {}
    if (
        job.status == AiSearchJob.STATUS_DONE
        and parsed.get("ok")
        and parsed.get("parse_ok")
        and want != stored
    ):
        groups, _fallback = search_by_parsed(parsed, sort=want)
        return hydrate_group_articles(groups)

    raw = job.groups or []
    return hydrate_group_articles(list(raw))
