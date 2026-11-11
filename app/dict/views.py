import re
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import TemplateView

from .helpers import (
    KRL_ABC,
    MAX_SEARCH_QUERY_LEN,
    build_pagination_hints,
    prepare_rus_query,
)
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
    refine_clickable = True
    wide_equals_exact = False
    if direction == "rus":
        (
            page_obj,
            found_count,
            narrowing,
            direct_ids,
            related_queries,
            wide_equals_exact,
        ) = search_by_translate_linked(prepare_rus_query(query), page, f)
        possible = []
        has_direct = bool(direct_ids)
        # Explicit ?f=: bare URL redirects to exact (if any) or all.
        if f is None:
            target = "exact" if has_direct else "all"
            return redirect("/search/%s/1?f=%s" % (quote(query), target))
        # Wide listing identical to exact — keep users on ?f=exact.
        if wide_equals_exact and f == "all":
            return redirect("/search/%s/1?f=exact" % quote(query))
        # Badge in refine heading: only for an active narrowing tag.
        if f not in ("exact", "all"):
            for tag in narrowing:
                if tag["key"] == f:
                    active_label = tag["label"]
                    break
            if active_label is None:
                active_label = f
        # When wide==exact, refine stays available on the exact screen.
        refine_clickable = f != "exact" or wide_equals_exact
        t_query = "?f=%s" % quote(f)
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
        "refine_clickable": refine_clickable,
        "wide_equals_exact": wide_equals_exact,
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
    found_count = 0

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
        if content.page_obj is not None:
            found_count = content.page_obj.paginator.count

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
        "found_count": found_count,
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
    found_count = (
        content.page_obj.paginator.count if content.page_obj is not None else 0
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
        "found_count": found_count,
        "ontology": "true",
    }
    return render(request, "ontology_view.html", context)


def page_not_found(request, exception=None):
    context = {
        "ABC": KRL_ABC,
    }
    return render(request, "404.html", context, status=404)


def classification_survey_status(request):
    """GET — whether the visitor survey is enabled."""
    from dict.classification_survey import survey_enabled

    return JsonResponse({"enabled": survey_enabled()})


def classification_survey_task(request):
    """GET — three eligible articles + field catalog for one respondent."""
    from dict.classification_survey import build_task_payload, survey_enabled

    if request.method != "GET":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    if not survey_enabled():
        return JsonResponse({"error": "disabled"}, status=404)
    key = (request.GET.get("key") or "").strip()
    if len(key) < 8 or len(key) > 64:
        return JsonResponse({"error": "bad_key"}, status=400)
    payload = build_task_payload(key)
    if len(payload["articles"]) < 1:
        return JsonResponse({"error": "no_articles"}, status=503)
    return JsonResponse(payload)


def classification_survey_submit(request):
    """POST JSON — store up to three control answers for a respondent."""
    import json

    from dict.classification_survey import survey_enabled, validate_and_store_answers

    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    if not survey_enabled():
        return JsonResponse({"error": "disabled"}, status=404)
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "bad_json"}, status=400)
    key = (body.get("key") or "").strip()
    if len(key) < 8 or len(key) > 64:
        return JsonResponse({"error": "bad_key"}, status=400)
    answers = body.get("answers")
    try:
        result = validate_and_store_answers(key, answers)
    except (ValueError, TypeError, KeyError) as exc:
        return JsonResponse({"error": "bad_answers", "detail": str(exc)}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "stored": result["stored"],
            "model_fields": result.get("model_fields") or [],
        }
    )
