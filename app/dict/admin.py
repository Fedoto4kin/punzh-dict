from django.contrib import admin
from django.utils.html import strip_tags
from dict.services import normalization
from django.utils.html import format_html


from .models import Article


class ArticleAdm(admin.ModelAdmin):

    fields = ('_word', 'word_normalized', 'article_html')

    list_display = ('_word', '_article_html')

    readonly_fields = ["_word",]
    search_fields = ('word',)
    exclude = ("first_letter", "text_search", 'first_trigram')


    @staticmethod
    def _article_html(self):
        return strip_tags(self.article_html)


    def _word(self, obj):
        return format_html("<b>{word}</b>", word=normalization(obj.word))

    _word.short_description = 'Заголовок (в норм. орф.)'


admin.site.register(Article, ArticleAdm)