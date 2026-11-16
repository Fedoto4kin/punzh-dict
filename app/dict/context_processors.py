from django.conf import settings
from django.urls import NoReverseMatch, reverse


def classification_survey(request):
    return {
        "classification_survey_enabled": bool(
            getattr(settings, "CLASSIFICATION_SURVEY", False)
        ),
    }


def _is_android_ua(user_agent: str) -> bool:
    ua = user_agent or ""
    # Exclude common desktop / bot noise; keep phones and tablets.
    if "Android" not in ua:
        return False
    if "Windows" in ua or "X11" in ua or "Macintosh" in ua:
        return False
    return True


def _is_home_page(request) -> bool:
    """True only for `/` (not letter index `/a/`, search, etc.)."""
    match = getattr(request, "resolver_match", None)
    if match is None or match.url_name != "index":
        return False
    return not match.kwargs.get("letter")


def _tracked_apk_url() -> str:
    """Banner link goes through Django (counter); file stays on nginx."""
    try:
        return reverse("apk_download")
    except NoReverseMatch:
        return getattr(
            settings,
            "MOBILE_APP_APK_URL",
            "/mobile-pack/punzh-dict-latest.apk",
        )


def mobile_app(request):
    """Soft promo for Android browsers on the home page only."""
    promote = bool(getattr(settings, "MOBILE_APP_PROMOTE", False))
    show = bool(
        promote
        and _is_home_page(request)
        and _is_android_ua(request.META.get("HTTP_USER_AGENT", ""))
    )
    return {
        "mobile_app_banner": show,
        "mobile_app_apk_url": _tracked_apk_url(),
        "mobile_app_rustore_url": (
            getattr(settings, "MOBILE_APP_RUSTORE_URL", "") or ""
        ).strip(),
        "mobile_app_version": (
            getattr(settings, "MOBILE_APP_VERSION", "") or ""
        ).strip(),
    }
