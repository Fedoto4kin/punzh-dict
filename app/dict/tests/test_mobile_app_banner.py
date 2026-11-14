import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import RequestFactory, SimpleTestCase, override_settings

from dict.context_processors import (
    _is_android_ua,
    _load_apk_manifest,
    mobile_app,
)


class AndroidUaTests(SimpleTestCase):
    def test_phone_android(self):
        ua = (
            "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Mobile Safari/537.36"
        )
        self.assertTrue(_is_android_ua(ua))

    def test_tablet_android(self):
        ua = (
            "Mozilla/5.0 (Linux; Android 12; SM-T870) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        self.assertTrue(_is_android_ua(ua))

    def test_iphone(self):
        ua = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
            "Mobile/15E148 Safari/604.1"
        )
        self.assertFalse(_is_android_ua(ua))

    def test_desktop(self):
        ua = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.assertFalse(_is_android_ua(ua))


class MobileAppContextTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        _load_apk_manifest.cache_clear()

    def tearDown(self):
        _load_apk_manifest.cache_clear()

    def _write_manifest(self, root: Path, version="1.0.0"):
        root.mkdir(parents=True, exist_ok=True)
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "version": version,
                    "version_code": 19,
                    "filename": "punzh-dict.apk",
                    "sha256": "abc",
                    "size": 1,
                }
            ),
            encoding="utf-8",
        )
        (root / "punzh-dict.apk").write_bytes(b"apk")

    def test_banner_for_android_when_apk_published(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest(root)
            with override_settings(
                MOBILE_APP_PROMOTE=True,
                DOWNLOADS_ROOT=root,
                MOBILE_APP_APK_URL="/downloads/punzh-dict.apk",
                MOBILE_APP_RUSTORE_URL="https://www.rustore.ru/catalog/app/x",
            ):
                req = self.factory.get(
                    "/",
                    HTTP_USER_AGENT=(
                        "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
                        "AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"
                    ),
                )
                ctx = mobile_app(req)
                self.assertTrue(ctx["mobile_app_banner"])
                self.assertEqual(ctx["mobile_app_version"], "1.0.0")
                self.assertTrue(ctx["mobile_app_rustore_url"])

    def test_no_banner_on_desktop(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest(root)
            with override_settings(MOBILE_APP_PROMOTE=True, DOWNLOADS_ROOT=root):
                req = self.factory.get(
                    "/",
                    HTTP_USER_AGENT=(
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                self.assertFalse(mobile_app(req)["mobile_app_banner"])

    def test_no_banner_without_manifest(self):
        with TemporaryDirectory() as tmp:
            with override_settings(MOBILE_APP_PROMOTE=True, DOWNLOADS_ROOT=Path(tmp)):
                req = self.factory.get(
                    "/",
                    HTTP_USER_AGENT=(
                        "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
                        "AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"
                    ),
                )
                self.assertFalse(mobile_app(req)["mobile_app_banner"])
