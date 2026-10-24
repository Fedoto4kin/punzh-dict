"""
Serialize AI search events for JSONL (REPL) and durable AiSearchLog (alpha).
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def serialize_ai_search_event(parse_result, groups=None, fallback_count=None):
    """One JSON-serializable record; groups/fallback filled by caller."""
    meta = parse_result.get("meta") or {}
    return {
        "query_raw": parse_result.get("query", ""),
        "parse_ok": parse_result.get("parse_ok", False),
        "ok": parse_result.get("ok", False),
        "error": parse_result.get("error"),
        "display": parse_result.get("display", ""),
        "parsed": {
            "lexical": parse_result.get("lexical", []),
            "focus": parse_result.get("focus", []),
            "related": parse_result.get("related", []),
            "fields": parse_result.get("fields", []),
            "tags": parse_result.get("tags", []),
            "place": parse_result.get("place"),
            "dialect": parse_result.get("dialect"),
            "dropped": parse_result.get("dropped", []),
        },
        "warnings": parse_result.get("warnings", []),
        # raw LLM blob stays out of DB; optional for JSONL callers
        "raw": parse_result.get("raw"),
        "groups_json": groups or [],
        "fallback_count": fallback_count,
        "model_query": meta.get("model", ""),
        "prompt_version": meta.get("prompt_version", ""),
        "latency_ms": meta.get("latency_ms"),
    }


def logging_enabled():
    return bool(getattr(settings, "AI_SEARCH_LOG_QUERIES", False))


def feedback_ui_enabled():
    return bool(getattr(settings, "AI_SEARCH_FEEDBACK", False))


def persist_ai_search_log(
    *,
    job,
    parse_result=None,
    groups_serialized=None,
):
    """
    Write one AiSearchLog for a finished job (done or error). Idempotent per job_id.
    Does not store raw LLM text. Returns the log row or None if logging is off.
    """
    if not logging_enabled():
        return None

    from dict.models import AiSearchLog

    job_uuid = job.id
    existing = AiSearchLog.objects.filter(job_id=job_uuid).first()
    if existing is not None:
        return existing

    if parse_result:
        event = serialize_ai_search_event(
            parse_result,
            groups=(
                groups_serialized
                if groups_serialized is not None
                else (job.groups or [])
            ),
            fallback_count=(
                job.fallback_count
                if job.fallback_count is not None
                else parse_result.get("fallback_count")
            ),
        )
        err = event.get("error") or job.error or ""
        error = (err if isinstance(err, str) else str(err))[:200]
    else:
        parsed = job.parsed or {}
        err = job.error or parsed.get("error") or ""
        error = (err if isinstance(err, str) else str(err))[:200]
        event = {
            "query_raw": job.query or "",
            "parse_ok": bool(parsed.get("parse_ok")),
            "ok": bool(parsed.get("ok")),
            "error": error,
            "display": (parsed.get("display") or "")[:500],
            "parsed": {
                "lexical": parsed.get("lexical") or [],
                "focus": parsed.get("focus") or [],
                "related": parsed.get("related") or [],
                "fields": parsed.get("fields") or [],
                "tags": parsed.get("tags") or [],
                "place": parsed.get("place"),
                "dialect": parsed.get("dialect"),
                "dropped": parsed.get("dropped") or [],
            },
            "groups_json": (
                groups_serialized
                if groups_serialized is not None
                else (job.groups or [])
            ),
            "fallback_count": job.fallback_count,
            "model_query": "",
            "prompt_version": "",
            "latency_ms": None,
        }

    try:
        return AiSearchLog.objects.create(
            job_id=job_uuid,
            query_raw=(event.get("query_raw") or job.query or "")[:300],
            parsed_json=event.get("parsed") or {},
            groups_json=event.get("groups_json") or [],
            display=(event.get("display") or "")[:500],
            parse_ok=bool(event.get("parse_ok")),
            ok=bool(event.get("ok")),
            error=error,
            fallback_count=event.get("fallback_count"),
            model_query=(event.get("model_query") or "")[:120],
            prompt_version=(event.get("prompt_version") or "")[:32],
            latency_ms=event.get("latency_ms"),
            session_key=(job.client_key or "")[:64],
        )
    except Exception:
        logger.exception("failed to persist AiSearchLog for job %s", job_uuid)
        return None


def log_for_job(job_id):
    """Lookup durable log by job UUID, or None."""
    from dict.models import AiSearchLog

    if not job_id:
        return None
    return AiSearchLog.objects.filter(job_id=job_id).first()
