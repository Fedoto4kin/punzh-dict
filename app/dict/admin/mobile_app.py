from django.contrib import admin

from dict.models import ApkDownloadStat


@admin.register(ApkDownloadStat)
class ApkDownloadStatAdm(admin.ModelAdmin):
    list_display = ("id", "count", "updated_at")
    fields = ("count", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not ApkDownloadStat.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
