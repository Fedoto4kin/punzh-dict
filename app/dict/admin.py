import re

from django.contrib import admin
from django.db import models
from django.forms import Textarea
from django.utils.html import format_html

from .helpers import normalization
from .models import (
    Article,
    ArticleAddition,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleLink,
    SemanticField,
    Source,
    Tag,
)


class ArticleLinkInline(admin.TabularInline):
    model = ArticleLink
    fk_name = "from_article"
    extra = 0
    verbose_name = "Связь"
    verbose_name_plural = "Смотрите также"


class ArticleLinkReverseInline(admin.TabularInline):
    model = ArticleLink
    fk_name = "to_article"
    extra = 0
    can_delete = False
    readonly_fields = ("from_article_link",)
    fields = ("from_article_link",)
    verbose_name = "Связь"
    verbose_name_plural = "На эту статью указывают"

    def has_add_permission(self, request, obj=None):
        return False

    def from_article_link(self, obj):
        url = obj.from_article.get_admin_url()
        return format_html('<a href="{}">{}</a>', url, obj.from_article.word)

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
        models.TextField: {"widget": Textarea(attrs={"rows": 4, "cols": 160})},
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
    exclude = ("first_letter", "text_search", "first_trigram")

    # Order matters: the reorder JS expects the four editorial inlines first
    # (indexes 0..3) and moves the "tail" fieldset to right after index 3.
    inlines = [
        TranslateInline,  # 0 - Переводы
        ArticleIndexTagInline,  # 1 - Пометы (служебные отметки)
        ArticleLinkInline,  # 2 - Смотрите также
        ArticleLinkReverseInline,  # 3 - На эту статью указывают
        ArticleAdditionInline,  # 4 - Дополнения (not in the requested list)
    ]

    formfield_overrides = {
        models.TextField: {"widget": Textarea(attrs={"rows": 4, "cols": 160})},
    }

    class Media:
        js = ("admin/js/article_field_reorder.js",)

    def get_search_results(self, request, queryset, search_term):

        queryset, use_distinct = super(ArticleAdm, self).get_search_results(
            request, queryset, search_term
        )
        try:
            search_term_as_int = int(search_term)
        except ValueError:
            pass
        else:
            queryset |= self.model.objects.filter(age=search_term_as_int)
        return queryset, use_distinct

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
    list_display = ("id", "name", "parent", "sorting")
    list_filter = ("parent",)
    search_fields = ("name", "definition")
    ordering = ("sorting", "name")
