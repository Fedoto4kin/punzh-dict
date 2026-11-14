import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings


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


@lru_cache(maxsize=4)
def _load_apk_manifest(mtime_ns: int) -> dict | None:
    del mtime_ns  # cache key only
    root = Path(getattr(settings, "DOWNLOADS_ROOT", ""))
    path = root / "manifest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _apk_manifest() -> dict | None:
    root = Path(getattr(settings, "DOWNLOADS_ROOT", ""))
    path = root / "manifest.json"
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return None
    return _load_apk_manifest(mtime_ns)


def mobile_app(request):
    """Offer RuStore / APK only to Android browsers when a pack is published."""
    promote = bool(getattr(settings, "MOBILE_APP_PROMOTE", False))
    manifest = _apk_manifest() if promote else None
    show = bool(
        promote and manifest and _is_android_ua(request.META.get("HTTP_USER_AGENT", ""))
    )
    return {
        "mobile_app_banner": show,
        "mobile_app_apk_url": getattr(
            settings, "MOBILE_APP_APK_URL", "/downloads/punzh-dict.apk"
        ),
        "mobile_app_rustore_url": (
            getattr(settings, "MOBILE_APP_RUSTORE_URL", "") or ""
        ).strip(),
        "mobile_app_version": (manifest or {}).get("version") or "",
    }
