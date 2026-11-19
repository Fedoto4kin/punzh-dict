from django.test import TestCase
from django.urls import reverse


class ElectronicPageTests(TestCase):
    def test_electronic_page_ok(self):
        r = self.client.get(reverse("electronic"))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn("Об электронной версии", body)
        self.assertIn('id="about"', body)
        self.assertIn('id="history"', body)
        self.assertIn('id="participants"', body)

    def test_team_redirects_to_electronic_participants(self):
        r = self.client.get(reverse("team"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/electronic/#participants")
