from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Count, Q
from django.forms import Textarea
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .ai.classify_bg import (
    article_has_ontology_markup,
    schedule_classify_article,
)
from .ai.ontology_status import (
    BUCKET_MARKED,
    BUCKET_PENDING,
    BUCKET_SKIP,
    filter_ontology_bucket,
    ontology_content_pos_label,
    ontology_material_label,
)
from .helpers import normalization
from .models import (
    Article,
    ArticleAddition,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleLink,
    ArticleSemanticField,
    OntologyQueueArticle,
    SemanticField,
    Source,
    Tag,
)
from .search import krl_article_ids
from .search_debug import explain_rus_search
from .tag_highlight import format_article_html
from .translation_browser import (
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

# CodeMirror 5 + js-beautify vendored under static/admin/vendor (no CDN).
_CM = "admin/vendor/codemirror"


class HtmlSourceWidget(Textarea):
    def __init__(self, attrs=None):
        default = {"rows": 8, "cols": 160, "class": "article-html-source"}
        if attrs:
            extra_class = attrs.get("class", "")
            merged = {**default, **attrs}
            merged["class"] = f"{default['class']} {extra_class}".strip()
            attrs = merged
        else:
            attrs = default
        super().__init__(attrs=attrs)

    class Media:
        css = {
            "all": (
                f"{_CM}/codemirror.min.css",
                "admin/css/article_html_editor.css",
            )
        }
        js = (
            f"{_CM}/codemirror.min.js",
            f"{_CM}/mode/xml/xml.min.js",
            f"{_CM}/mode/javascript/javascript.min.js",
            f"{_CM}/mode/css/css.min.js",
            f"{_CM}/mode/htmlmixed/htmlmixed.min.js",
            "admin/vendor/js-beautify/beautify-html.min.js",
            "admin/js/article_html_editor.js",
        )


class ArticleLinkInline(admin.TabularInline):
    model = ArticleLink
    fk_name = "from_article"
    extra = 0
    fields = ("to_article", "kind")
    autocomplete_fields = ("to_article",)
    verbose_name = "Исходящая отсылка"
    verbose_name_plural = "Смотрите также (см./ср./от из этой статьи)"

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj=obj, **kwargs)
        widget = formset.form.base_fields["to_article"].widget
        widget.can_add_related = False
        widget.can_change_related = False
        widget.can_delete_related = False
        return formset


class ArticleLinkReverseInline(admin.TabularInline):
    model = ArticleLink
    fk_name = "to_article"
    extra = 0
    can_delete = False
    readonly_fields = ("from_article_link", "kind")
    fields = ("from_article_link", "kind")
    verbose_name = "Входящая отсылка"
    verbose_name_plural = "На эту статью указывают (только просмотр)"

    def has_add_permission(self, request, obj=None):
        return False

    def from_article_link(self, obj):
        url = obj.from_article.get_admin_url()
        return format_html(
            '<a href="{}">{}</a>', url, normalization(obj.from_article.word)
        )

    from_article_link.short_description = "Статья‑источник"


class TranslateInline(admin.TabularInline):
    extra = 0
    model = ArticleIndexTranslate


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


class ArticleAdditionInline(admin.StackedInline):
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "article_html",
                    "source",
                    "source_detalization",
                ]
            },
        ),
    ]
    formfield_overrides = {
        models.TextField: {"widget": HtmlSourceWidget()},
    }

    extra = 0
    model = ArticleAddition


class ArticleIndexTagInline(admin.TabularInline):
    model = ArticleIndexTag
    extra = 0
    autocomplete_fields = ("tag",)
    verbose_name = "Помета"
    verbose_name_plural = "Пометы (служебные отметки)"

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        widget = formset.form.base_fields["tag"].widget
        widget.can_add_related = False
        widget.can_change_related = False
        widget.can_delete_related = False
        return formset


class ArticleSemanticFieldInline(admin.TabularInline):
    model = ArticleSemanticField
    extra = 0
    can_delete = False
    fields = ("field_name", "from_translation", "field_definition")
    readonly_fields = ("field_name", "from_translation", "field_definition")
    verbose_name = "Смысловое поле"
    verbose_name_plural = "Смысловые поля (онтология)"

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def field_name(self, obj):
        return obj.field.name

    field_name.short_description = "Смысловое поле"

    def field_definition(self, obj):
        return obj.field.definition

    field_definition.short_description = "Определение"


class OntologyMarkupFilter(admin.SimpleListFilter):
    """
    Buckets: all / marked / pending / skip. See dict.ai.ontology_status.

    Explicit «все» (?ontology=all) — Django's default All clears the param,
    and OntologyQueueAdm would redirect bare URLs back to pending.
    """

    title = "Онтология"
    parameter_name = "ontology"
    # Sentinel so «все» keeps a query param (avoids pending redirect).
    ALL = "all"

    def lookups(self, request, model_admin):
        return (
            (self.ALL, "все"),
            (BUCKET_MARKED, "размечены"),
            (BUCKET_PENDING, "ждут разметки"),
            (BUCKET_SKIP, "разметка не нужна"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value in (BUCKET_MARKED, BUCKET_PENDING, BUCKET_SKIP):
            return filter_ontology_bucket(queryset, value)
        return queryset

    def choices(self, changelist):
        # Drop Django's built-in All (empty param); we use ontology=all instead.
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == str(lookup),
                "query_string": changelist.get_query_string(
                    {self.parameter_name: lookup}
                ),
                "display": title,
            }


@admin.register(Source)
class SourceAdm(admin.ModelAdmin):
    exclude = ("css",)


@admin.register(Article)
class ArticleAdm(admin.ModelAdmin):

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
        if schedule_classify_article(obj.pk, user_id=request.user.pk):
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
        classified = article_has_ontology_markup(article)
        if schedule_classify_article(article.pk, user_id=request.user.pk):
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

        form = super(ArticleAdm, self).get_form(request, obj, **kwargs)

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

    def _article_html(self, obj):
        # Same pipeline as translation browser / public cards.
        html = obj.article_html or ""
        if not html:
            return ""
        return format_html(
            '<div class="article-html-preview">{}</div>',
            mark_safe(format_article_html(html)),
        )

    _article_html.short_description = "Словарная статья"
    linked_article_deprecated.short_description = "См. (устарело)"

    def _word(self, obj):
        if obj.word_normalized:
            return format_html(
                "<s>{word}</s> <b>{word_norm}</b>",
                word=normalization(obj.word),
                word_norm=obj.word_normalized,
            )
        return format_html("<b>{word}</b>", word=normalization(obj.word))

    _word.short_description = "Заголовок (в норм. орф.)"


@admin.register(Tag)
class TagAdm(admin.ModelAdmin):
    list_display = ("id", "name", "tag", "type")
    list_filter = ("type",)
    search_fields = ("^name", "^tag")
    ordering = ("type", "sorting", "name")


@admin.register(SemanticField)
class SemanticFieldAdm(admin.ModelAdmin):
    list_display = ("id", "name", "parent", "sorting", "article_count", "site_link")
    search_fields = ("name", "definition")
    ordering = ("sorting", "name")
    readonly_fields = ("name", "definition", "parent", "sorting")
    change_list_template = "admin/dict/semanticfield/change_list.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["ontology_queue_url"] = reverse(
            "admin:dict_ontologyqueuearticle_changelist"
        )
        return super().changelist_view(request, extra_context)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_save"] = False
        extra_context["show_save_and_continue"] = False
        extra_context["show_save_and_add_another"] = False
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_article_count=Count("assignments"))

    def article_count(self, obj):
        return obj._article_count

    article_count.admin_order_field = "_article_count"
    article_count.short_description = "Статей"

    def site_link(self, obj):
        return format_html('<a href="/ontology/{}/" target="_blank">🔗</a>', obj.pk)

    site_link.short_description = "Сайт"


@admin.register(OntologyQueueArticle)
class OntologyQueueAdm(admin.ModelAdmin):
    """
    Markup queue: same three ontology buckets, opens the editorial Article form.
    """

    list_display = (
        "id",
        "_word",
        "ontology_fields",
        "ontology_material",
        "ontology_pos",
        "_article_html",
    )
    list_filter = (OntologyMarkupFilter,)
    search_fields = ("word",)
    ordering = ("-id",)
    list_per_page = 50
    actions = ("reclassify_selected",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Переклассифицировать")
    def reclassify_selected(self, request, queryset):
        scheduled = 0
        already = 0
        for article_id in queryset.values_list("pk", flat=True):
            if schedule_classify_article(article_id, user_id=request.user.pk):
                scheduled += 1
            else:
                already += 1
        if scheduled:
            self.message_user(
                request,
                f"Онтология: в очередь поставлено {scheduled}.",
                level=messages.INFO,
            )
        if already:
            self.message_user(
                request,
                f"Онтология: уже выполняется для {already}.",
                level=messages.WARNING,
            )
        if not scheduled and not already:
            self.message_user(
                request,
                "Онтология: ничего не выбрано.",
                level=messages.WARNING,
            )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _ontology_field_count=Count("semantic_assignments", distinct=True),
            _ontology_from_translation_count=Count(
                "semantic_assignments",
                filter=Q(semantic_assignments__from_translation=True),
                distinct=True,
            ),
            _ontology_kw_count=Count("articlekeyword", distinct=True),
        )

    def changelist_view(self, request, extra_context=None):
        # Only redirect bare GETs; POST actions must keep the selected rows.
        if request.method == "GET" and "ontology" not in request.GET:
            params = request.GET.copy()
            params["ontology"] = BUCKET_PENDING
            return HttpResponseRedirect(f"{request.path}?{params.urlencode()}")
        return super().changelist_view(request, extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return HttpResponseRedirect(
            reverse("admin:dict_article_change", args=[object_id])
        )

    def ontology_fields(self, obj):
        """from_translation / total (e.g. 1/2)."""
        total = getattr(obj, "_ontology_field_count", None)
        if total is None:
            total = obj.semantic_assignments.count()
        if not total:
            return "—"
        from_tr = getattr(obj, "_ontology_from_translation_count", None)
        if from_tr is None:
            from_tr = obj.semantic_assignments.filter(from_translation=True).count()
        return f"{from_tr}/{total}"

    ontology_fields.short_description = "Поля"
    ontology_fields.admin_order_field = "_ontology_field_count"

    def ontology_material(self, obj):
        return ontology_material_label(obj)

    ontology_material.short_description = "Материал"

    def ontology_pos(self, obj):
        return ontology_content_pos_label(obj)

    ontology_pos.short_description = "POS"

    def _word(self, obj):
        if obj.word_normalized:
            return format_html(
                "<s>{word}</s> <b>{word_norm}</b>",
                word=normalization(obj.word),
                word_norm=obj.word_normalized,
            )
        return format_html("<b>{word}</b>", word=normalization(obj.word))

    _word.short_description = "Заголовок"

    def _article_html(self, obj):
        html = obj.article_html or ""
        if not html:
            return ""
        return format_html(
            '<div class="article-html-preview">{}</div>',
            mark_safe(format_article_html(html)),
        )

    _article_html.short_description = "Словарная статья"

    class Media:
        css = {"all": ("admin/css/article_html_preview.css",)}


# Sidebar under Dict: Слова, Переводы, then the rest (alpha).
# Semantic fields + pending queue are pulled into a nested «Онтология» block.
_DICT_MODEL_ORDER = {
    "article": 0,
    "articleindextranslate": 1,
}

_ONTOLOGY_SIDEBAR_MODELS = frozenset({"semanticfield", "ontologyqueuearticle"})
_ONTOLOGY_SIDEBAR_ORDER = {
    "semanticfield": 0,
    "ontologyqueuearticle": 1,
}


def ontology_pending_count() -> int:
    """Articles in the «ждут разметки» bucket (sidebar badge)."""
    qs = OntologyQueueArticle.objects.annotate(
        _ontology_field_count=Count("semantic_assignments", distinct=True),
        _ontology_kw_count=Count("articlekeyword", distinct=True),
    )
    return filter_ontology_bucket(qs, BUCKET_PENDING).count()


def _dict_app_list(request):
    app_list = admin.AdminSite.get_app_list(admin.site, request)
    pending_n = ontology_pending_count()
    result = []
    for app in app_list:
        if app.get("app_label") != "dict":
            result.append(app)
            continue
        ontology_models = []
        dict_models = []
        for model in app["models"]:
            key = model["object_name"].lower()
            if key in _ONTOLOGY_SIDEBAR_MODELS:
                if key == "ontologyqueuearticle":
                    # Badge = pending only; the changelist also has marked/skip.
                    model = {**model, "name": f"Разметка ({pending_n})"}
                ontology_models.append(model)
            else:
                dict_models.append(model)
        dict_models.sort(
            key=lambda m: (
                _DICT_MODEL_ORDER.get(m["object_name"].lower(), 50),
                m["name"].lower(),
            )
        )
        ontology_models.sort(
            key=lambda m: (
                _ONTOLOGY_SIDEBAR_ORDER.get(m["object_name"].lower(), 50),
                m["name"].lower(),
            )
        )
        app = {**app, "models": dict_models}
        result.append(app)
        if ontology_models:
            first_url = next(
                (m.get("admin_url") for m in ontology_models if m.get("admin_url")),
                app.get("app_url"),
            )
            result.append(
                {
                    "name": "Онтология",
                    "app_label": "dict_ontology",
                    "app_url": first_url,
                    "has_module_perms": True,
                    "models": ontology_models,
                }
            )
    return result


admin.site.get_app_list = _dict_app_list
