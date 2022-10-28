import re

from django.contrib import admin
from django.utils.html import format_html

from .helpers import normalization
from .models import Article, ArticleIndexTranslate, Source


class TranslateInline(admin.TabularInline):
    extra = 0
    model = ArticleIndexTranslate

@admin.register(Source)
class SourceAdm(admin.ModelAdmin):

    exclude = ("css",)

@admin.register(Article)
class ArticleAdm(admin.ModelAdmin):

    fields = ('_word', 'word_normalized', 'word',
              'article_html', '_article_html', 'source',
              'source_detalization', 'linked_article')

    list_display = ('id', '_word', '_article_html',)
    readonly_fields = ["_word", '_article_html',]

    sorting = ['id',]

    search_fields = ('word',)
    exclude = ("first_letter", "text_search", 'first_trigram')

    inlines = [
        TranslateInline
    ]

    def get_search_results(self, request, queryset, search_term):

        queryset, use_distinct = super(ArticleAdm, self).get_search_results(request, queryset, search_term)
        try:
            search_term_as_int = int(search_term)
        except ValueError:
            pass
        else:
            queryset |= self.model.objects.filter(age=search_term_as_int)
        return queryset, use_distinct

    def get_form(self, request, obj=None, **kwargs):

        form = super(ArticleAdm, self).get_form(request, obj, **kwargs)
        f0 = form.base_fields["linked_article"]
        f0.widget.can_add_related = False
        f0.widget.can_change_related = False
        f0.widget.can_delete_related = False

        f1 = form.base_fields["source"]
        f1.widget.can_add_related = False
        f1.widget.can_change_related = False
        f1.widget.can_delete_related = False
        
        return form

    # def get_search_results(self, request, queryset, search_term):
    #
    #

    #
    #     pks0 = ArticleIndexWord.objects.filter(word__istartswith=search).values_list('article_id', flat=True)
    #     queryset = Article.objects.filter(pk__in=pks0).all()
    #
    #     return queryset, False


    def _article_html(self, obj):
        return format_html(obj.article_html)

    _article_html.short_description = 'Словарная статья'

    def _word(self, obj):
        if obj.word_normalized:
            return format_html("<s>{word}</s> <b>{word_norm}</b>", word=normalization(obj.word), word_norm=obj.word_normalized)
        return format_html("<b>{word}</b>", word=normalization(obj.word))

    _word.short_description = 'Заголовок (в норм. орф.)'

