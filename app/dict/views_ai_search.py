"""
HTTP for /ai-search/ (async job + poll + feedback).

Lexical /ontology/ and classification survey stay in dict.views.
"""

import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse

from dict.helpers import KRL_ABC, prepare_rus_query
from dict.search import search_by_translate_linked


def _ai_client_key(request):
    if not request.session.session_key:
        request.session.save()
    return (request.session.session_key or "")[:64]


def _ai_job_for_session(request, job_id):
    """
    Load AiSearchJob by id only if it belongs to this session (client_key).
    Expired / missing / other session → None (caller returns 404).
    """
    from dict.models import AiSearchJob

    job = AiSearchJob.objects.filter(pk=job_id).first()
    if job is None or job.status == AiSearchJob.STATUS_EXPIRED:
        return None
    key = _ai_client_key(request)
    # Jobs created without a key (tests/legacy) stay readable only with empty key.
    if (job.client_key or "") != key:
        return None
    return job


def _ai_dict_linked_lemmas(parsed):
    """
    Lemmas from the parse that exist as exact translations → /search/ links.
    Order: focus → lexical (e.g. «кошка») → related; deduped.
    """
    from dict.ai.rank import lemmas_with_exact_translate

    parsed = parsed or {}
    out = []
    seen = set()
    for bucket in (
        parsed.get("focus") or [],
        parsed.get("lexical") or [],
        parsed.get("related") or [],
    ):
        for w in lemmas_with_exact_translate(bucket):
            key = w.lower()
            if key not in seen:
                out.append(w)
                seen.add(key)
    return out


def _ai_feedback_context(job):
    """log_id + whether to show the inline thumbs widget (done jobs only)."""
    from dict.ai.telemetry import feedback_ui_enabled, log_for_job
    from dict.models import AiSearchFeedback

    ctx = {
        "ai_log_id": "",
        "ai_feedback_show": False,
        "ai_feedback_url": "",
    }
    if job is None or job.status != "done" or not feedback_ui_enabled():
        return ctx
    # No thumbs when LLM/infra failed («Разбор по смыслу недоступен…»).
    parsed = job.parsed or {}
    if not parsed.get("ok"):
        return ctx
    log = log_for_job(job.id)
    if log is None or AiSearchFeedback.objects.filter(log_id=log.id).exists():
        return ctx
    ctx["ai_log_id"] = str(log.id)
    ctx["ai_feedback_show"] = True
    ctx["ai_feedback_url"] = reverse("ai_search_feedback")
    return ctx


def _ai_search_shell_context(request, *, query="", sort="relevance", job=None):
    from dict.ai.rank import SORT_ALPHA, SORT_RELEVANCE, normalize_sort
    from dict.ai.search import _field_meta

    sort = normalize_sort(sort)
    ctx = {
        "ABC": KRL_ABC,
        "ai_search": "true",
        "query": query,
        "sort": sort,
        "sort_relevance": SORT_RELEVANCE,
        "sort_alpha": SORT_ALPHA,
        "parsed": None,
        "groups": [],
        "ontology_fields": [],
        "fallback_count": None,
        "fallback_page": None,
        "fallback_found": 0,
        "job_id": "",
        "job_status": "",
        "pending_query": "",
        "related_linked": [],
        "ai_log_id": "",
        "ai_feedback_show": False,
        "ai_feedback_url": "",
    }
    if job is not None:
        from dict.ai.jobs import hydrate_job_groups, mark_stale_running

        mark_stale_running(job)
        job.refresh_from_db()
        ctx["job_id"] = str(job.id)
        ctx["job_status"] = job.status
        ctx["query"] = job.query or query
        # Prefer requested sort (UI toggle) over the sort stored when job ran.
        ctx["sort"] = sort
        if job.status == "done":
            parsed = job.parsed or {}
            groups = hydrate_job_groups(job, sort=sort)
            ctx["parsed"] = parsed
            ctx["groups"] = groups
            ctx["related_linked"] = _ai_dict_linked_lemmas(parsed)
            ctx["fallback_count"] = job.fallback_count
            ctx["ontology_fields"] = _field_meta(list(parsed.get("fields") or []))
            if job.fallback_count is not None and job.fallback_count > 0:
                page_obj, found_count, *_rest = search_by_translate_linked(
                    prepare_rus_query(job.query or ""), 1
                )
                ctx["fallback_page"] = page_obj
                ctx["fallback_found"] = found_count
            ctx.update(_ai_feedback_context(job))
        elif job.status == "error":
            ctx["parsed"] = job.parsed or {
                "ok": False,
                "parse_ok": False,
                "display": "",
                "error": job.error or "error",
            }
    return ctx


def ai_search(request):
    """
    Smart search shell: JS → POST /ai-search/jobs/ → poll (no sync LLM path).
    ?job=<uuid> shows a finished or in-flight job without re-parse.
    """
    from dict.ai.rank import normalize_sort

    raw = request.GET.get("query", "")
    query = raw.strip()
    sort = normalize_sort(request.GET.get("sort"))
    job_id = (request.GET.get("job") or "").strip()

    if job_id:
        job = _ai_job_for_session(request, job_id)
        if job is None:
            ctx = _ai_search_shell_context(request, query=query, sort=sort)
            ctx["job_missing"] = True
            return render(request, "ai_search.html", ctx)
        return render(
            request,
            "ai_search.html",
            _ai_search_shell_context(request, query=query, sort=sort, job=job),
        )

    if not query:
        return render(
            request,
            "ai_search.html",
            _ai_search_shell_context(request, query="", sort=sort),
        )

    ctx = _ai_search_shell_context(request, query=query, sort=sort)
    ctx["pending_query"] = query
    return render(request, "ai_search.html", ctx)


def ai_search_job_create(request):
    """POST /ai-search/jobs/ → 202 {id, status}."""
    import json

    from dict.ai.jobs import create_job, rate_limit_ok
    from dict.ai.rank import normalize_sort

    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client_key = _ai_client_key(request)
    if not rate_limit_ok(client_key):
        return JsonResponse({"error": "rate_limited"}, status=429)

    query = ""
    sort = "relevance"
    ctype = (request.content_type or "").split(";")[0].strip().lower()
    if ctype == "application/json":
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "bad_json"}, status=400)
        query = (body.get("query") or "").strip()
        sort = normalize_sort(body.get("sort"))
    else:
        query = (request.POST.get("query") or "").strip()
        sort = normalize_sort(request.POST.get("sort"))

    if not query:
        return JsonResponse({"error": "empty_query"}, status=400)

    job = create_job(query, sort=sort, client_key=client_key)
    return JsonResponse(
        {"id": str(job.id), "status": job.status, "query": job.query},
        status=202,
    )


def ai_search_job_status(request, job_id):
    """GET /ai-search/jobs/<uuid>/ → JSON status (+ parsed/groups when done)."""
    from dict.ai.jobs import mark_stale_running
    from dict.models import AiSearchJob

    job = _ai_job_for_session(request, job_id)
    if job is None:
        return JsonResponse({"error": "not_found"}, status=404)

    mark_stale_running(job)
    job.refresh_from_db()

    from dict.ai.search import _field_meta

    payload = {
        "id": str(job.id),
        "status": job.status,
        "query": job.query,
        "sort": job.sort,
        "error": job.error or None,
    }
    if job.status == AiSearchJob.STATUS_DONE:
        parsed = job.parsed or {}
        payload["parsed"] = parsed
        payload["groups"] = job.groups
        payload["fallback_count"] = job.fallback_count
        payload["ontology_fields"] = _field_meta(list(parsed.get("fields") or []))
        payload["html_ready"] = True
    elif job.status == AiSearchJob.STATUS_ERROR:
        payload["parsed"] = job.parsed
        payload["ontology_fields"] = []
    return JsonResponse(payload)


def ai_search_job_partial(request, job_id):
    """GET /ai-search/jobs/<uuid>/partial/ → HTML fragment of result groups."""
    from dict.ai.jobs import hydrate_job_groups, mark_stale_running
    from dict.ai.rank import normalize_sort
    from dict.ai.search import _field_meta
    from dict.models import AiSearchJob

    job = _ai_job_for_session(request, job_id)
    if job is None:
        return HttpResponse("Not found", status=404)

    mark_stale_running(job)
    job.refresh_from_db()
    if job.status != AiSearchJob.STATUS_DONE:
        return HttpResponse("Not ready", status=409)

    sort = normalize_sort(request.GET.get("sort") or job.sort)
    parsed = job.parsed or {}
    groups = hydrate_job_groups(job, sort=sort)
    ontology_fields = _field_meta(list(parsed.get("fields") or []))
    related_linked = _ai_dict_linked_lemmas(parsed)
    fallback_page = None
    fallback_found = 0
    if job.fallback_count is not None and job.fallback_count > 0:
        fallback_page, fallback_found, *_rest = search_by_translate_linked(
            prepare_rus_query(job.query or ""), 1
        )

    ctx = {
        "query": job.query,
        "parsed": parsed,
        "groups": groups,
        "ontology_fields": ontology_fields,
        "related_linked": related_linked,
        "fallback_count": job.fallback_count,
        "fallback_page": fallback_page,
        "fallback_found": fallback_found,
        "sort": sort,
    }
    ctx.update(_ai_feedback_context(job))
    return render(request, "ai_search_results.html", ctx)


def ai_search_feedback(request):
    """POST /ai-search/feedback/ → upsert AiSearchFeedback for this session's log."""
    import json

    from dict.ai.telemetry import feedback_ui_enabled
    from dict.models import AiSearchFeedback, AiSearchLog

    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    if not feedback_ui_enabled():
        return JsonResponse({"error": "disabled"}, status=404)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "bad_json"}, status=400)

    log_id = (body.get("log_id") or "").strip()
    vote = (body.get("vote") or "").strip()
    if vote not in (AiSearchFeedback.VOTE_UP, AiSearchFeedback.VOTE_DOWN):
        return JsonResponse({"error": "bad_vote"}, status=400)

    log = AiSearchLog.objects.filter(pk=log_id).first()
    if log is None:
        return JsonResponse({"error": "not_found"}, status=404)
    key = _ai_client_key(request)
    if (log.session_key or "") != key:
        return JsonResponse({"error": "not_found"}, status=404)

    reasons = body.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = []
    allowed = set(AiSearchFeedback.REASON_CHOICES)
    reasons = [r for r in reasons if r in allowed][:5]
    if vote == AiSearchFeedback.VOTE_UP:
        reasons = []
    comment = (body.get("comment") or "").strip()[:500]
    if vote == AiSearchFeedback.VOTE_UP:
        comment = ""

    fb, _created = AiSearchFeedback.objects.update_or_create(
        log=log,
        defaults={
            "vote": vote,
            "reasons": reasons,
            "comment": comment,
        },
    )
    return JsonResponse(
        {"ok": True, "vote": fb.vote, "log_id": str(log.id)},
        status=200,
    )
