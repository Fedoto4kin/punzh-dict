import re
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import TemplateView

from .helpers import KRL_ABC, build_pagination_hints
from .search import (
    Content,
    get_tags_by_ids_distinct,
    get_tags_by_type,
    search_by_pointer,
    search_by_semantic_field,
    semantic_fields_with_counts,
    search_by_tags_smart,
    search_by_translate_linked,
    search_possible,
    word_search,
    detect_direction,
    compatible_disable,
    format_krl_filter_query,
    parse_ontology_all_param,
    tag_filters_from_request,
)
from .models import Article, ArticleIndexTag, SemanticField, Tag

# Align with AI job bound (dict.ai.jobs.MAX_QUERY_LEN); caps ILIKE/token cost.
MAX_SEARCH_QUERY_LEN = 300
SEARCH_RATE_LIMIT_PER_MINUTE = 60


def _client_ip(request):
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR") or ""


def _search_rate_limit_ok(request):
    """Per-IP minute counter (locmem/default cache; per-worker). Off in DEBUG."""
    if settings.DEBUG:
        return True
    ip = _client_ip(request)
    if not ip:
        return True
    key = f"lex_search_rl:{ip}"
    try:
        n = cache.incr(key)
    except ValueError:
        cache.add(key, 1, timeout=60)
        return True
    return n <= SEARCH_RATE_LIMIT_PER_MINUTE


def _clip_search_query(query):
    return (query or "").strip()[:MAX_SEARCH_QUERY_LEN]


class StaticView(TemplateView):

    template_name = None

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)


def index(request, letter=None, page=1):

    def _get404():
        _context = {
            "ABC": KRL_ABC,
            "letter": letter.upper(),
        }
        return render(request, "404.html", _context, status=404)

    if not letter:
        count = Article.objects.count()
        return render(
            request,
            "index.html",
            {"articles_count": f"{count:,}".replace(",", "\u00a0")},
        )

    if letter.upper() not in KRL_ABC:
        return _get404()

    content = search_by_pointer(letter, page)
    if page > content.page_obj.paginator.num_pages or page < 1:
        return _get404()

    current_trigram = ""
    if len(content.trigrams_dict) > 1:
        current_trigram = f" ({content.trigrams_dict.get(page)})"
    context = {
        "ABC": KRL_ABC,
        "letter": letter.upper(),
        "last_page_word": content.last_page_word,
        "first_page_word": content.first_page_word,
        "trigrams": content.trigrams_dict,
        "page_obj": content.page_obj,
        "current_trigram": current_trigram,
    }
    return render(request, "article_list.html", context)


def search_proc(request):
    if not _search_rate_limit_ok(request):
        return HttpResponseBadRequest("Too many search requests")
    query = request.GET.get("query", "")
    if len(query.strip()):
        query = re.sub(r"[^\w\-\s\.\?]", "", query)
        query = _clip_search_query(query)
        if not query:
            return render(request, "search.html", {"search": "true"})
        return redirect("/search/" + quote(query))
    else:
        return render(request, "search.html", {"search": "true"})


def search(request, query="", page=1):
    if not _search_rate_limit_ok(request):
        return HttpResponseBadRequest("Too many search requests")
    query = _clip_search_query(query)
    direction = detect_direction(query)
    f = request.GET.get("f") or None
    active_label = None
    tag_filter_groups = []
    phrase_filter = None
    t_query = ""
    if direction == "rus":
        translation_table = str.maketrans({"ё": "е", "?": "%", ".": "_"})
        page_obj, found_count, narrowing, direct_ids, related_queries = (
            search_by_translate_linked(query.translate(translation_table), page, f)
        )
        possible = []
        # подпись активного фильтра для badge в заголовке
        if f == "exact":
            active_label = "точные соответствия"
        elif f:
            for tag in narrowing:
                if tag["key"] == f:
                    active_label = tag["label"]
                    break
            if active_label is None:
                active_label = f
    else:
        direction = "krl"
        tag_ids, phrase = tag_filters_from_request(request)
        (
            page_obj,
            found_count,
            tag_filter_groups,
            phrase_filter,
            t_query,
        ) = word_search(query, page, tag_ids, phrase)
        narrowing = []
        direct_ids = set()
        related_queries = []
        possible = []
        if not len(page_obj.object_list):
            possible = search_possible(query)
    trigrams = build_pagination_hints(
        page_obj.paginator.object_list, page_obj.paginator.per_page
    )
    context = {
        "ABC": KRL_ABC,
        "query": query,
        "search": "true",
        "page_obj": page_obj,
        "possible": possible,
        "narrowing": narrowing,
        "has_direct": bool(direct_ids),
        "related_queries": related_queries,
        "active_f": f,
        "active_label": active_label,
        "found_count": found_count,
        "direction": direction,
        "trigrams": trigrams,
        "tag_filter_groups": tag_filter_groups,
        "phrase_filter": phrase_filter,
        "t_query": t_query,
        "tag_list_base": "/search/%s/" % quote(query),
    }
    return render(request, "search.html", context)


def tag_search(request, tags="", page=1):
    content = Content()

    tmp_list = set(tags.split(","))
    try:
        tag_ids = [int(x.strip()) for x in tmp_list]
    except:
        tag_ids = []

    all_tags = get_tags_by_type()
    geo_tags = get_tags_by_type(1)
    linguistic_tags = get_tags_by_type(2)
    tag_tags = get_tags_by_type(3)
    dialect_tags = get_tags_by_type(4)
    other_tags = get_tags_by_type(5)

    tags_selected = get_tags_by_ids_distinct(tag_ids)

    if len(tag_ids):
        content = search_by_tags_smart(
            by_geo=list(set(geo_tags.values_list("pk", flat=True)) & set(tag_ids)),
            by_tags=list(set(tag_tags.values_list("pk", flat=True)) & set(tag_ids)),
            by_dialect=list(
                set(dialect_tags.values_list("pk", flat=True)) & set(tag_ids)
            ),
            by_ling=list(
                set(linguistic_tags.values_list("pk", flat=True)) & set(tag_ids)
            ),
            by_other=list(set(other_tags.values_list("pk", flat=True)) & set(tag_ids)),
            page=page,
        )

    context = {
        "ABC": KRL_ABC,
        "tagIds": tag_ids,
        "tags_selected": tags_selected,
        "allTags": {
            "all": all_tags,
            "geo": geo_tags,
            "linguistic": linguistic_tags,
            "tag": tag_tags,
            "dialect": dialect_tags,
            "other": other_tags,
        },
        "query": ",".join(map(str, tag_ids)),
        "page_obj": content.page_obj,
        "trigrams": content.trigrams_dict,
    }
    return render(request, "tags.html", context)


def tags_compatible(request, tags=""):
    try:
        selected = [int(x) for x in tags.split(",") if x.strip()]
    except ValueError:
        return JsonResponse({"disable": []})
    return JsonResponse({"disable": compatible_disable(selected)})


def robots_txt(request):
    """Serve /robots.txt without APPEND_SLASH → <letter>/ catch-all."""
    body = Path(__file__).with_name("robots.txt").read_text(encoding="utf-8")
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


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
    from django.urls import reverse

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
                translation_table = str.maketrans({"ё": "е", "?": "%", ".": "_"})
                page_obj, found_count, *_rest = search_by_translate_linked(
                    (job.query or "").translate(translation_table), 1
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
        translation_table = str.maketrans({"ё": "е", "?": "%", ".": "_"})
        fallback_page, fallback_found, *_rest = search_by_translate_linked(
            (job.query or "").translate(translation_table), 1
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


def ontology_index(request):
    context = {
        "ABC": KRL_ABC,
        "fields": semantic_fields_with_counts(),
        "ontology": "true",
    }
    return render(request, "ontology.html", context)


def ontology_view(request, field_id, page=1):
    field = get_object_or_404(SemanticField, pk=field_id)
    tag_ids, phrase = tag_filters_from_request(request)
    include_all = parse_ontology_all_param(request.GET.get("all"))
    content = search_by_semantic_field(
        field.id, page, tag_ids, phrase, include_all=include_all
    )
    context = {
        "ABC": KRL_ABC,
        "field": field,
        "all_fields": semantic_fields_with_counts(),
        "page_obj": content.page_obj,
        "trigrams": content.trigrams_dict,
        "tag_filter_groups": content.tag_filter_groups or [],
        "phrase_filter": content.phrase_filter,
        "t_query": content.t_query or "",
        "tag_list_base": "/ontology/%s/" % field.id,
        "include_all": include_all,
        "has_tag_or_phrase_filter": bool(tag_ids or phrase),
        "mode_query": format_krl_filter_query([], False, include_all=include_all),
        "mode_tr_query": format_krl_filter_query(tag_ids, phrase, include_all=False),
        "mode_all_query": format_krl_filter_query(tag_ids, phrase, include_all=True),
        "ontology": "true",
    }
    return render(request, "ontology_view.html", context)


def page_not_found(request, exception=None):
    context = {
        "ABC": KRL_ABC,
    }
    return render(request, "404.html", context, status=404)
