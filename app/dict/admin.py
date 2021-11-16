from django.contrib import admin
from dict.services import normalization
from django.utils.html import format_html, html_safe


from .models import Article


class ArticleAdm(admin.ModelAdmin):

    fields = ('_word', 'word_normalized', 'word', 'article_html')

    list_display = ('_word', '_article_html')

    readonly_fields = ["_word"]

    search_fields = ('word',)
    exclude = ("first_letter", "text_search", 'first_trigram')


    def _article_html(self, obj):
        return format_html(obj.article_html)

    _article_html.short_description = 'Словарная статья'

    def _word(self, obj):
        return format_html("<b>{word}</b>", word=normalization(obj.word))

    _word.short_description = 'Заголовок (в норм. орф.)'


admin.site.register(Article, ArticleAdm)