from django.contrib import admin
from django.utils.html import strip_tags

from .models import Article


class ArticleAdm(admin.ModelAdmin):

    list_display = ('word', '_article_html')
    search_fields = ('word',)
    exclude = ("first_letter", "text_search")
    readonly_fields = ("first_trigram",)

    @staticmethod
    def _article_html(self):
        return strip_tags(self.article_html)


admin.site.register(Article, ArticleAdm)