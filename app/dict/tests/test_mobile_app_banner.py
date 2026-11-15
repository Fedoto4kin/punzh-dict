from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import ResolverMatch

from dict.context_processors import _is_android_ua, mobile_app


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


def _attach_match(request, url_name, **kwargs):
    request.resolver_match = ResolverMatch(
        func=lambda: None,
        args=(),
        kwargs=kwargs,
        url_name=url_name,
    )
    return request


class MobileAppContextTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.android_ua = (
            "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"
        )

    def test_banner_on_home_for_android(self):
        with override_settings(
            MOBILE_APP_PROMOTE=True,
            MOBILE_APP_APK_URL="/mobile-pack/punzh-dict-latest.apk",
            MOBILE_APP_RUSTORE_URL="https://www.rustore.ru/catalog/app/x",
            MOBILE_APP_VERSION="1.0.3",
        ):
            req = _attach_match(
                self.factory.get("/", HTTP_USER_AGENT=self.android_ua),
                "index",
            )
            ctx = mobile_app(req)
            self.assertTrue(ctx["mobile_app_banner"])
            self.assertEqual(ctx["mobile_app_version"], "1.0.3")
            self.assertEqual(
                ctx["mobile_app_apk_url"], "/mobile-pack/punzh-dict-latest.apk"
            )
            self.assertTrue(ctx["mobile_app_rustore_url"])

    def test_no_banner_on_letter_index(self):
        with override_settings(MOBILE_APP_PROMOTE=True):
            req = _attach_match(
                self.factory.get("/a/", HTTP_USER_AGENT=self.android_ua),
                "index",
                letter="a",
            )
            self.assertFalse(mobile_app(req)["mobile_app_banner"])

    def test_no_banner_on_search(self):
        with override_settings(MOBILE_APP_PROMOTE=True):
            req = _attach_match(
                self.factory.get("/search/", HTTP_USER_AGENT=self.android_ua),
                "search_proc",
            )
            self.assertFalse(mobile_app(req)["mobile_app_banner"])

    def test_no_banner_on_desktop(self):
        with override_settings(MOBILE_APP_PROMOTE=True):
            req = _attach_match(
                self.factory.get(
                    "/",
                    HTTP_USER_AGENT=(
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                    ),
                ),
                "index",
            )
            self.assertFalse(mobile_app(req)["mobile_app_banner"])

    def test_no_banner_when_disabled(self):
        with override_settings(MOBILE_APP_PROMOTE=False):
            req = _attach_match(
                self.factory.get("/", HTTP_USER_AGENT=self.android_ua),
                "index",
            )
            self.assertFalse(mobile_app(req)["mobile_app_banner"])
