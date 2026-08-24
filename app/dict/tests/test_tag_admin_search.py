from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from ..admin import TagAdm
from ..models import Tag


class TagAdminSearchTestCase(TestCase):
    def setUp(self):
        self.admin = TagAdm(Tag, AdminSite())
        self.factory = RequestFactory()
        Tag.objects.create(tag="всг.", name="весьегонский говор", type=4)
        Tag.objects.create(tag="сг.", name="другая помета", type=4)
        Tag.objects.create(tag="бран.", name="бранное", type=3)

    def _tags(self, term):
        request = self.factory.get("/admin/dict/tag/")
        qs, _ = self.admin.get_search_results(request, Tag.objects.all(), term)
        return set(qs.values_list("tag", flat=True))

    def test_prefix_matches_tag_field(self):
        self.assertEqual(self._tags("всг"), {"всг."})

    def test_mid_substring_does_not_match(self):
        self.assertEqual(self._tags("сг"), {"сг."})

    def test_prefix_matches_name_field(self):
        self.assertEqual(self._tags("бранн"), {"бран."})
