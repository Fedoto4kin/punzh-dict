from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from dict.management.commands.set_apk_download_count import count_apk_hits_in_log
from dict.models import ApkDownloadStat


class ApkDownloadViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @override_settings(MOBILE_APP_APK_URL="/mobile-pack/punzh-dict-latest.apk")
    def test_increments_and_redirects(self):
        url = reverse("apk_download")
        r1 = self.client.get(url)
        self.assertEqual(r1.status_code, 302)
        self.assertEqual(r1["Location"], "/mobile-pack/punzh-dict-latest.apk")
        self.assertEqual(ApkDownloadStat.get_solo().count, 1)

        r2 = self.client.get(url)
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(ApkDownloadStat.get_solo().count, 2)

    def test_set_count(self):
        ApkDownloadStat.set_count(17)
        self.assertEqual(ApkDownloadStat.get_solo().count, 17)


class ApkLogParseTests(TestCase):
    def test_counts_get_200_and_206(self):
        sample = """
1.2.3.4 - - [15/Nov/2026:12:00:00 +0300] "GET /mobile-pack/punzh-dict-latest.apk HTTP/1.1" 200 1234 "-" "Mozilla"
1.2.3.4 - - [15/Nov/2026:12:00:01 +0300] "GET /mobile-pack/punzh-dict-latest.apk HTTP/1.1" 206 512 "-" "Mozilla"
1.2.3.4 - - [15/Nov/2026:12:00:02 +0300] "HEAD /mobile-pack/punzh-dict-latest.apk HTTP/1.1" 200 0 "-" "Mozilla"
1.2.3.4 - - [15/Nov/2026:12:00:03 +0300] "GET /mobile-pack/manifest.json HTTP/1.1" 200 99 "-" "Mozilla"
1.2.3.4 - - [15/Nov/2026:12:00:04 +0300] "GET /mobile-pack/punzh-dict-latest.apk HTTP/1.1" 404 0 "-" "Mozilla"
"""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "access.log"
            path.write_text(sample, encoding="utf-8")
            self.assertEqual(count_apk_hits_in_log(path), 2)
