from django.contrib import admin
from django.db import models
from django.db.models import Count
from django.forms import Textarea
from django.utils.html import format_html

from .helpers import normalization
from .models import (
    Article,
    ArticleAddition,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleLink,
    ArticleSemanticField,
    SemanticField,
    Source,
    Tag,
)
from .search import krl_article_ids

# CodeMirror 5 (CDN) — HTML source highlighting in admin, no WYSIWYG.
CODEMIRROR_VERSION = "5.65.16"
CODEMIRROR_CDN = (
    f"https://cdnjs.cloudflare.com/ajax/libs/codemirror/{CODEMIRROR_VERSION}"
)


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
                f"{CODEMIRROR_CDN}/codemirror.min.css",
                "admin/css/article_html_editor.css",
            )
        }
        js = (
            f"{CODEMIRROR_CDN}/codemirror.min.js",
            f"{CODEMIRROR_CDN}/mode/xml/xml.min.js",
            f"{CODEMIRROR_CDN}/mode/javascript/javascript.min.js",
            f"{CODEMIRROR_CDN}/mode/css/css.min.js",
            f"{CODEMIRROR_CDN}/mode/htmlmixed/htmlmixed.min.js",
            "https://cdnjs.cloudflare.com/ajax/libs/js-beautify/1.14.11/beautify-html.min.js",
            "admin/js/article_html_editor.js",
        )


class ArticleLinkInline(admin.TabularInline):
    model = ArticleLink
    fk_name = "from_article"
    extra = 0
    autocomplete_fields = ("to_article",)
    verbose_name = "Исходящая отсылка"
    verbose_name_plural = "Смотрите также (см./ср. из этой статьи)"

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
    readonly_fields = ("from_article_link",)
    fields = ("from_article_link",)
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
    list_filter = ("semantic_assignments__field",)
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
        js = ("admin/js/article_field_reorder.js",)

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
        return format_html(obj.article_html)

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

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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
