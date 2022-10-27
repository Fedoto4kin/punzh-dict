import re
from django.contrib import admin
from django.utils.html import format_html, html_safe

from .models import Article, ArticleIndexTranslate, ArticleIndexWord, Source
from .helpers import normalization

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
    list_display = ('_word', '_article_html',)

    readonly_fields = ["_word", '_article_html',]

    search_fields = ('word',)
    exclude = ("first_letter", "text_search", 'first_trigram')

    inlines = [
        TranslateInline
    ]

    def get_search_results(self, request, queryset, search_term):

        search = re.sub(r'[^\w\-\s\.\?]', '', search_term) \
            .replace('š', 's') \
            .replace('č', 'c') \
            .replace('ž', 'z') \
            .replace('?', '%') \
            .replace('.', '_')

        pks0 = ArticleIndexWord.objects.filter(word__istartswith=search).values_list('article_id', flat=True)
        queryset = Article.objects.filter(pk__in=pks0).all()

        return queryset, False


    def _article_html(self, obj):
        return format_html(obj.article_html)

    _article_html.short_description = 'Словарная статья'

    def _word(self, obj):
        if obj.word_normalized:
            return format_html("<s>{word}</s> <b>{word_norm}</b>", word=normalization(obj.word), word_norm=obj.word_normalized)
        return format_html("<b>{word}</b>", word=normalization(obj.word))

    _word.short_description = 'Заголовок (в норм. орф.)'
