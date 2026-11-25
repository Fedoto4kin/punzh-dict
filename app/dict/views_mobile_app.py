"""Tracked Android APK download and the public «О приложении» page."""

from django.conf import settings
from django.http import HttpResponseRedirect
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from dict.mobile_app_info import read_app_manifest, resolve_mobile_app_version
from dict.models import ApkDownloadStat


@require_GET
def apk_download(request):
    """Increment the APK download counter and redirect to the real file URL."""
    ApkDownloadStat.increment()
    target = getattr(
        settings,
        "MOBILE_APP_APK_URL",
        "/mobile-pack/punzh-dict-latest.apk",
    )
    return HttpResponseRedirect(target)


class MobileAppView(TemplateView):
    """Static page: offline Android app — install paths and update tips."""

    template_name = "staticPages/mobile_app.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        manifest = read_app_manifest()
        context["mobile_app_version"] = resolve_mobile_app_version(manifest)
        return context
