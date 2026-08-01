import re

from django.contrib import admin
from django.db import models
from django.forms import Textarea
from django.utils.html import format_html

from .helpers import normalization
from .models import Article, ArticleAddition, ArticleIndexTranslate, ArticleLink, Source


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


@admin.register(Source)
class SourceAdm(admin.ModelAdmin):
    exclude = ("css",)


@admin.register(Article)
class ArticleAdm(admin.ModelAdmin):

    fields = (
        "_word",
        "word_normalized",
        "word",
        "article_html",
        "_article_html",
        "source",
        "source_detalization",
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

    inlines = [
        ArticleAdditionInline,
        TranslateInline,
        ArticleLinkInline,
        ArticleLinkReverseInline,
    ]

    formfield_overrides = {
        models.TextField: {"widget": Textarea(attrs={"rows": 4, "cols": 160})},
    }

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
