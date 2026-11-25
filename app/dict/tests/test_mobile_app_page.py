import json
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from dict.mobile_app_info import read_app_manifest, resolve_mobile_app_version


class MobileAppManifestTests(SimpleTestCase):
    def test_read_and_resolve_from_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app-manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "version_name": "1.1.1",
                        "version_code": 27,
                        "apk_url": "https://example.test/app/apk/",
                    }
                ),
                encoding="utf-8",
            )
            with override_settings(
                MOBILE_APP_MANIFEST_PATH=str(path),
                MOBILE_APP_VERSION="0.0.1",
            ):
                doc = read_app_manifest()
                self.assertEqual(doc["version_name"], "1.1.1")
                self.assertEqual(resolve_mobile_app_version(), "1.1.1")

    def test_fallback_to_env_when_manifest_missing(self):
        with override_settings(
            MOBILE_APP_MANIFEST_PATH="/nonexistent/app-manifest.json",
            MOBILE_APP_VERSION="1.0.3",
        ):
            self.assertIsNone(read_app_manifest())
            self.assertEqual(resolve_mobile_app_version(), "1.0.3")

    def test_invalid_manifest_falls_back(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app-manifest.json"
            path.write_text("{not-json", encoding="utf-8")
            with override_settings(
                MOBILE_APP_MANIFEST_PATH=str(path),
                MOBILE_APP_VERSION="2.0.0",
            ):
                self.assertIsNone(read_app_manifest())
                self.assertEqual(resolve_mobile_app_version(), "2.0.0")


class MobileAppPageTests(TestCase):
    def test_mobile_app_page_ok(self):
        with override_settings(
            MOBILE_APP_MANIFEST_PATH="/nonexistent/app-manifest.json",
            MOBILE_APP_VERSION="1.1.1",
            MOBILE_APP_RUSTORE_URL="https://www.rustore.ru/catalog/app/host.punzh.punzh_dict",
        ):
            r = self.client.get(reverse("mobile_app"))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn("О приложении", body)
        self.assertIn('id="about"', body)
        self.assertIn('id="install"', body)
        self.assertIn('id="db-update"', body)
        self.assertIn("1.1.1", body)
        self.assertIn("Актуальная версия", body)
        self.assertIn("badge badge-primary", body)
        self.assertIn("/app/apk/", body)
        self.assertIn("rustore.ru", body)
        self.assertIn("Проверить и загрузить обновление БД", body)
