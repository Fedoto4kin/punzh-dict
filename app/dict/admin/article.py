from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Count
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html

from dict.ai import classify_bg
from dict.models import Article, Source
from dict.search import krl_article_ids
from dict.search_debug import explain_rus_search

from .inlines import (
    ArticleAdditionInline,
    ArticleIndexTagInline,
    ArticleLinkInline,
    ArticleLinkReverseInline,
    ArticleSemanticFieldInline,
    TranslateInline,
)
from .mixins import ArticlePreviewMixin
from .widgets import HtmlSourceWidget


@admin.register(Source)
class SourceAdm(admin.ModelAdmin):
    exclude = ("css",)


@admin.register(Article)
class ArticleAdm(ArticlePreviewMixin, admin.ModelAdmin):

    # NOTE: Django admin always renders ALL fieldsets first and ALL inlines
    # afterwards, so inlines cannot be placed *between* form fields natively.
    # We split the fields into a "head" and a "tail" fieldset; a small JS
    # snippet (see the Media class below) moves the "tail" group down so it
    # sits right after the editorial inlines, giving the desired field order.
    fieldsets = (
        (
            None,
            {
                "classes": ("field-head",),
                "fields": (
                    "_word",  # Заголовок (в норм. орф.)
                    "word_normalized",  # Коррекция заголовка
                    "word",  # Слово (ориг.)
                ),
            },
        ),
        (
            None,
            {
                "classes": ("field-tail",),
                "fields": (
                    "article_html",  # Словарная статья (html)
                    "_article_html",  # Словарная статья (rendered)
                    "source",  # Источник
                    "source_detalization",  # Уточнение источника
                ),
            },
        ),
    )

    list_display = (
        "id",
        "_word",
        "_article_html",
    )
    readonly_fields = [
        "_word",
        "_article_html",
        "linked_article_deprecated",
    ]

    sorting = [
        "-id",
    ]

    search_fields = ("word",)
    exclude = ("first_letter",)

    # Order matters: the reorder JS parks the "tail" fieldset after
    # "На эту статью указывают". Semantic fields sit last (change only;
    # omitted on add via get_inlines).
    inlines = [
        TranslateInline,  # Переводы
        ArticleIndexTagInline,  # Пометы (служебные отметки)
        ArticleLinkInline,  # Смотрите также
        ArticleLinkReverseInline,  # На эту статью указывают
        ArticleAdditionInline,  # Дополнения
        ArticleSemanticFieldInline,  # Смысловые поля (readonly, change only)
    ]

    def get_inlines(self, request, obj):
        inlines = super().get_inlines(request, obj)
        if obj is None:
            return [
                inline for inline in inlines if inline is not ArticleSemanticFieldInline
            ]
        return inlines

    formfield_overrides = {
        models.TextField: {"widget": HtmlSourceWidget()},
    }

    class Media:
        css = {"all": ("admin/css/article_html_preview.css",)}
        js = ("admin/js/article_field_reorder.js",)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "search-debug/",
                self.admin_site.admin_view(self.search_debug_view),
                name="dict_article_search_debug",
            ),
            path(
                "<path:object_id>/classify/",
                self.admin_site.admin_view(self.classify_view),
                name="dict_article_classify",
            ),
        ]
        return custom + urls

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id is not None:
            extra_context["show_ontology_classify"] = True
            article = (
                Article.objects.filter(pk=object_id)
                .annotate(
                    _ontology_field_count=Count("semantic_assignments", distinct=True),
                    _ontology_kw_count=Count("articlekeyword", distinct=True),
                )
                .first()
            )
            if article is not None:
                extra_context["ontology_classified"] = (
                    article._ontology_field_count > 0 or article._ontology_kw_count > 0
                )
            else:
                extra_context["show_ontology_classify"] = False
        return super().changeform_view(request, object_id, form_url, extra_context)

    def response_add(self, request, obj, post_url_continue=None):
        if classify_bg.schedule_classify_article(obj.pk, user_id=request.user.pk):
            self.message_user(
                request,
                "Онтология: разметка поставлена в очередь.",
                level=messages.INFO,
            )
        else:
            self.message_user(
                request,
                "Онтология: разметка уже выполняется.",
                level=messages.WARNING,
            )
        return super().response_add(request, obj, post_url_continue)

    def classify_view(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        article = get_object_or_404(Article, pk=object_id)
        if not self.has_change_permission(request, article):
            raise PermissionDenied
        classified = classify_bg.article_has_ontology_markup(article)
        if classify_bg.schedule_classify_article(article.pk, user_id=request.user.pk):
            msg = (
                "Онтология: переразметка поставлена в очередь."
                if classified
                else "Онтология: разметка поставлена в очередь."
            )
            self.message_user(request, msg, level=messages.INFO)
        else:
            self.message_user(
                request,
                "Онтология: разметка уже выполняется.",
                level=messages.WARNING,
            )
        return HttpResponseRedirect(
            reverse("admin:dict_article_change", args=[article.pk])
        )

    def search_debug_view(self, request):
        raw_query = (request.GET.get("q") or "").strip()
        f = request.GET.get("f") or None
        try:
            page = int(request.GET.get("p") or 1)
        except (TypeError, ValueError):
            page = 1

        result = explain_rus_search(raw_query, f=f, page=page) if raw_query else None
        context = {
            **self.admin_site.each_context(request),
            "title": "Отладка русского поиска",
            "opts": self.model._meta,
            "query": raw_query,
            "f": f or "",
            "result": result,
            "has_query": bool(raw_query),
        }
        return render(request, "admin/dict/article/search_debug.html", context)

    def get_search_results(self, request, queryset, search_term):
        term = (search_term or "").strip()
        if not term:
            # Autocomplete must not dump the whole dictionary; the changelist
            # with an empty search box still lists every article.
            if "autocomplete" in request.path:
                return queryset.none(), False
            return queryset, False
        return queryset.filter(pk__in=krl_article_ids(term)), False

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        f1 = form.base_fields["source"]
        f1.widget.can_add_related = False
        f1.widget.can_change_related = False
        f1.widget.can_delete_related = False

        return form

    def linked_article_deprecated(self, obj):
        if obj.linked_article:
            return format_html(
                "<span style='color:#999'>{}</span>", obj.linked_article.word
            )
        return format_html("<span style='color:#999'>—</span>")

    linked_article_deprecated.short_description = "См. (устарело)"


ArticleAdm._word.short_description = "Заголовок (в норм. орф.)"
