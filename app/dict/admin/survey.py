from django.contrib import admin

from dict.models import ClassificationSurveyResponse


@admin.register(ClassificationSurveyResponse)
class ClassificationSurveyResponseAdm(admin.ModelAdmin):
    list_display = (
        "id",
        "article",
        "decision",
        "fields_preview",
        "respondent_short",
        "created_at",
    )
    list_filter = ("decision", "created_at")
    search_fields = ("respondent_key", "article__word")
    readonly_fields = (
        "respondent_key",
        "article",
        "decision",
        "fields",
        "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def fields_preview(self, obj):
        names = obj.fields or []
        return ", ".join(names) if names else "—"

    fields_preview.short_description = "Поля"

    def respondent_short(self, obj):
        key = obj.respondent_key or ""
        return (key[:8] + "…") if len(key) > 8 else key

    respondent_short.short_description = "Respondent"
