"""Mobile app version / install URLs for the site promo and /app/ page."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings


def _manifest_path() -> Path | None:
    raw = (getattr(settings, "MOBILE_APP_MANIFEST_PATH", "") or "").strip()
    if not raw:
        return None
    return Path(raw)


def read_app_manifest(path: Path | None = None) -> dict | None:
    """Parse app-manifest.json written by punzh-dict-mobile publish_downloads.sh."""
    target = path if path is not None else _manifest_path()
    if target is None or not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def resolve_mobile_app_version(manifest: dict | None = None) -> str:
    """Prefer version_name from app-manifest.json; fall back to MOBILE_APP_VERSION."""
    doc = manifest if manifest is not None else read_app_manifest()
    if doc:
        name = doc.get("version_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return (getattr(settings, "MOBILE_APP_VERSION", "") or "").strip()
