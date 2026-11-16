from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from dict.models import ApkDownloadStat


@admin.register(ApkDownloadStat)
class ApkDownloadStatAdm(admin.ModelAdmin):
    """Singleton: sidebar shows «APK ↓ N»; open only to edit the seed."""

    fields = ("count", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not ApkDownloadStat.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = ApkDownloadStat.get_solo()
        return redirect(reverse("admin:dict_apkdownloadstat_change", args=[obj.pk]))
