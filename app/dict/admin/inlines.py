from django.contrib import admin
from django.db import models
from django.utils.html import format_html

from dict.helpers import normalization
from dict.models import (
    ArticleAddition,
    ArticleIndexTag,
    ArticleIndexTranslate,
    ArticleLink,
    ArticleSemanticField,
)

from .widgets import HtmlSourceWidget


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
