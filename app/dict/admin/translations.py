from django.contrib import admin
from django.shortcuts import render

from dict.models import ArticleIndexTranslate
from dict.translation_browser import (
    MODE_CONTAINS,
    MODE_EXACT,
    MODE_PREFIX,
    SORT_HIT,
    SORT_WORD,
    build_translation_cards,
    normalize_mode,
    normalize_sort,
    paginate_cards,
)


@admin.register(ArticleIndexTranslate)
class ArticleIndexTranslateAdm(admin.ModelAdmin):
    """
    Card browser: find articles by rus_word (exact / contains / prefix),
    show headword + HTML + full translation list. Day-to-day edits go
    through the article form inline; no standalone «Add» in the sidebar.
    """

    list_display = ("id", "rus_word", "article")
    search_fields = ("rus_word",)
    autocomplete_fields = ("article",)
    ordering = ("rus_word", "article_id")

    def has_module_permission(self, request):
        return request.user.is_staff

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        query = (request.GET.get("q") or "").strip()
        mode = normalize_mode(request.GET.get("mode"))
        sort = normalize_sort(request.GET.get("sort"), mode)
        try:
            page = int(request.GET.get("p") or 1)
        except (TypeError, ValueError):
            page = 1

        cards = build_translation_cards(query, mode=mode, sort=sort) if query else []
        page_obj = paginate_cards(cards, page=page) if cards else None

        context = {
            **self.admin_site.each_context(request),
            "title": "Переводы (индекс)",
            "opts": self.model._meta,
            "query": query,
            "mode": mode,
            "sort": sort,
            "page_obj": page_obj,
            "found_count": len(cards),
            "modes": (
                (MODE_EXACT, "точное"),
                (MODE_CONTAINS, "содержит"),
                (MODE_PREFIX, "префикс"),
            ),
            "sorts": (
                (SORT_WORD, "по заголовку"),
                (SORT_HIT, "по совпавшему переводу"),
            ),
            "has_query": bool(query),
        }
        if extra_context:
            context.update(extra_context)
        return render(
            request,
            "admin/dict/articleindextranslate/browse.html",
            context,
        )
