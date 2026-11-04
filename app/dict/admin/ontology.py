from django.contrib import admin, messages
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from dict.ai import classify_bg
from dict.ai.ontology_status import (
    BUCKET_MARKED,
    BUCKET_PENDING,
    BUCKET_SKIP,
    filter_ontology_bucket,
    ontology_content_pos_label,
    ontology_material_label,
)
from dict.models import OntologyQueueArticle, SemanticField

from .mixins import ArticlePreviewMixin


class OntologyMarkupFilter(admin.SimpleListFilter):
    """
    Buckets: all / marked / pending / skip. See dict.ai.ontology_status.

    Explicit «все» (?ontology=all) — Django's default All clears the param,
    and OntologyQueueAdm would redirect bare URLs back to pending.
    """

    title = "Онтология"
    parameter_name = "ontology"
    # Sentinel so «все» keeps a query param (avoids pending redirect).
    ALL = "all"

    def lookups(self, request, model_admin):
        return (
            (self.ALL, "все"),
            (BUCKET_MARKED, "размечены"),
            (BUCKET_PENDING, "ждут разметки"),
            (BUCKET_SKIP, "разметка не нужна"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value in (BUCKET_MARKED, BUCKET_PENDING, BUCKET_SKIP):
            return filter_ontology_bucket(queryset, value)
        return queryset

    def choices(self, changelist):
        # Drop Django's built-in All (empty param); we use ontology=all instead.
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == str(lookup),
                "query_string": changelist.get_query_string(
                    {self.parameter_name: lookup}
                ),
                "display": title,
            }


@admin.register(SemanticField)
class SemanticFieldAdm(admin.ModelAdmin):
    list_display = ("id", "name", "parent", "sorting", "article_count", "site_link")
    search_fields = ("name", "definition")
    ordering = ("sorting", "name")
    readonly_fields = ("name", "definition", "parent", "sorting")
    change_list_template = "admin/dict/semanticfield/change_list.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["ontology_queue_url"] = reverse(
            "admin:dict_ontologyqueuearticle_changelist"
        )
        return super().changelist_view(request, extra_context)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_save"] = False
        extra_context["show_save_and_continue"] = False
        extra_context["show_save_and_add_another"] = False
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_article_count=Count("assignments"))

    def article_count(self, obj):
        return obj._article_count

    article_count.admin_order_field = "_article_count"
    article_count.short_description = "Статей"

    def site_link(self, obj):
        return format_html('<a href="/ontology/{}/" target="_blank">🔗</a>', obj.pk)

    site_link.short_description = "Сайт"


@admin.register(OntologyQueueArticle)
class OntologyQueueAdm(ArticlePreviewMixin, admin.ModelAdmin):
    """
    Markup queue: same three ontology buckets, opens the editorial Article form.
    """

    list_display = (
        "id",
        "_word",
        "ontology_fields",
        "ontology_material",
        "ontology_pos",
        "_article_html",
    )
    list_filter = (OntologyMarkupFilter,)
    search_fields = ("word",)
    ordering = ("-id",)
    list_per_page = 50
    actions = ("reclassify_selected",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Переклассифицировать")
    def reclassify_selected(self, request, queryset):
        scheduled = 0
        already = 0
        for article_id in queryset.values_list("pk", flat=True):
            if classify_bg.schedule_classify_article(
                article_id, user_id=request.user.pk
            ):
                scheduled += 1
            else:
                already += 1
        if scheduled:
            self.message_user(
                request,
                f"Онтология: в очередь поставлено {scheduled}.",
                level=messages.INFO,
            )
        if already:
            self.message_user(
                request,
                f"Онтология: уже выполняется для {already}.",
                level=messages.WARNING,
            )
        if not scheduled and not already:
            self.message_user(
                request,
                "Онтология: ничего не выбрано.",
                level=messages.WARNING,
            )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _ontology_field_count=Count("semantic_assignments", distinct=True),
            _ontology_from_translation_count=Count(
                "semantic_assignments",
                filter=Q(semantic_assignments__from_translation=True),
                distinct=True,
            ),
            _ontology_kw_count=Count("articlekeyword", distinct=True),
        )

    def changelist_view(self, request, extra_context=None):
        # Only redirect bare GETs; POST actions must keep the selected rows.
        if request.method == "GET" and "ontology" not in request.GET:
            params = request.GET.copy()
            params["ontology"] = BUCKET_PENDING
            return HttpResponseRedirect(f"{request.path}?{params.urlencode()}")
        return super().changelist_view(request, extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return HttpResponseRedirect(
            reverse("admin:dict_article_change", args=[object_id])
        )

    def ontology_fields(self, obj):
        """from_translation / total (e.g. 1/2)."""
        total = getattr(obj, "_ontology_field_count", None)
        if total is None:
            total = obj.semantic_assignments.count()
        if not total:
            return "—"
        from_tr = getattr(obj, "_ontology_from_translation_count", None)
        if from_tr is None:
            from_tr = obj.semantic_assignments.filter(from_translation=True).count()
        return f"{from_tr}/{total}"

    ontology_fields.short_description = "Поля"
    ontology_fields.admin_order_field = "_ontology_field_count"

    def ontology_material(self, obj):
        return ontology_material_label(obj)

    ontology_material.short_description = "Материал"

    def ontology_pos(self, obj):
        return ontology_content_pos_label(obj)

    ontology_pos.short_description = "POS"

    class Media:
        css = {"all": ("admin/css/article_html_preview.css",)}


def ontology_pending_count() -> int:
    """Articles in the «ждут разметки» bucket (sidebar badge)."""
    qs = OntologyQueueArticle.objects.annotate(
        _ontology_field_count=Count("semantic_assignments", distinct=True),
        _ontology_kw_count=Count("articlekeyword", distinct=True),
    )
    return filter_ontology_bucket(qs, BUCKET_PENDING).count()
