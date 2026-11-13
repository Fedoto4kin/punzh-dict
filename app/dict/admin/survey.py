from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from dict.classification_survey import model_fields_for_article
from dict.models import ClassificationSurveyResponse
from dict.tag_highlight import format_article_html

_DECISION_LABELS = {
    ClassificationSurveyResponse.DECISION_NO_FIELD: "Ни одно поле не подходит",
    ClassificationSurveyResponse.DECISION_INSUFFICIENT: "Недостаточно информации",
}


def _field_names_html(names: list[str]):
    if not names:
        return "—"
    return format_html(
        "<ul style='margin:0;padding-left:1.2em'>{}</ul>",
        format_html_join("", "<li>{}</li>", ((n,) for n in names)),
    )


@admin.register(ClassificationSurveyResponse)
class ClassificationSurveyResponseAdm(admin.ModelAdmin):
    list_display = (
        "id",
        "article",
        "fields_preview",
        "created_at",
    )
    list_filter = ("decision", "created_at")
    search_fields = ("article__word",)
    fields = (
        "article_preview",
        "visitor_fields_display",
        "llm_fields_display",
        "created_at",
    )
    readonly_fields = fields
    ordering = ("-created_at",)

    class Media:
        css = {"all": ("admin/css/article_html_preview.css",)}

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("article")

    def has_add_permission(self, request):
        return False

    def fields_preview(self, obj):
        label = _DECISION_LABELS.get(obj.decision)
        if label:
            return label
        names = obj.fields or []
        return ", ".join(names) if names else "—"

    fields_preview.short_description = "Поля"

    def article_preview(self, obj):
        if not obj or not obj.article_id:
            return "—"
        art = obj.article
        word = (art.word_normalized or art.word or "").strip() or f"#{art.pk}"
        html = art.article_html or ""
        if html:
            body = mark_safe(format_article_html(html))
        else:
            body = "—"
        return format_html(
            '<p style="margin-top:0"><b>{}</b>'
            ' <span style="color:#666">(id {})</span></p>'
            '<div class="article-html-preview">{}</div>',
            word,
            art.pk,
            body,
        )

    article_preview.short_description = "Статья"

    def visitor_fields_display(self, obj):
        if not obj:
            return "—"
        label = _DECISION_LABELS.get(obj.decision)
        if label:
            return label
        return _field_names_html(obj.fields or [])

    visitor_fields_display.short_description = "Ответ посетителя"

    def llm_fields_display(self, obj):
        if not obj or not obj.article_id:
            return "—"
        return _field_names_html(model_fields_for_article(obj.article_id))

    llm_fields_display.short_description = "Поля LLM"
