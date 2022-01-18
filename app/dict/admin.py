from django.contrib import admin
from dict.services import normalization
from django.utils.html import format_html, html_safe


from .models import Article, ArticleIndexTranslate, Source

class TranslateInline(admin.TabularInline):
    extra = 0
    model = ArticleIndexTranslate

@admin.register(Source)
class SourceAdm(admin.ModelAdmin):
    pass

@admin.register(Article)
class ArticleAdm(admin.ModelAdmin):

    fields = ('_word', 'word_normalized', 'word',
              'article_html', '_article_html', 'source',
              'source_detalization',)
    list_display = ('_word', '_article_html',)

    readonly_fields = ["_word", '_article_html',]

    search_fields = ('word',)
    exclude = ("first_letter", "text_search", 'first_trigram')

    inlines = [
        TranslateInline
    ]

    def _article_html(self, obj):
        return format_html(obj.article_html)

    _article_html.short_description = 'Словарная статья'

    def _word(self, obj):
        if obj.word_normalized:
            return format_html("<s>{word}</s> <b>{word_norm}</b>", word=normalization(obj.word), word_norm=obj.word_normalized)
        return format_html("<b>{word}</b>", word=normalization(obj.word))

    _word.short_description = 'Заголовок (в норм. орф.)'
