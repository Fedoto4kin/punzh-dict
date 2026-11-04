from django.utils.html import format_html
from django.utils.safestring import mark_safe

from dict.helpers import normalization
from dict.tag_highlight import format_article_html


class ArticlePreviewMixin:
    """Shared list/change preview columns for Article-backed ModelAdmins."""

    def _word(self, obj):
        if obj.word_normalized:
            return format_html(
                "<s>{word}</s> <b>{word_norm}</b>",
                word=normalization(obj.word),
                word_norm=obj.word_normalized,
            )
        return format_html("<b>{word}</b>", word=normalization(obj.word))

    _word.short_description = "Заголовок"

    def _article_html(self, obj):
        html = obj.article_html or ""
        if not html:
            return ""
        return format_html(
            '<div class="article-html-preview">{}</div>',
            mark_safe(format_article_html(html)),
        )

    _article_html.short_description = "Словарная статья"
