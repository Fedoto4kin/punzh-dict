"""Tracked Android APK download (count + redirect to nginx file)."""

from django.conf import settings
from django.http import HttpResponseRedirect
from django.views.decorators.http import require_GET

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
