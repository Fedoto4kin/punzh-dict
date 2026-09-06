from django.test import TestCase

from dict.models import Tag
from dict.tag_highlight import (
    clear_italic_tag_cache,
    format_article_html,
    get_italic_tag_values,
    highlight_tags,
)


class TagHighlightTestCase(TestCase):
    def setUp(self):
        clear_italic_tag_cache()
        Tag.objects.create(tag="s", name="substantivum", type=2, sorting=1)
        Tag.objects.create(tag="перен.", name="переносно", type=3, sorting=1)
        Tag.objects.create(tag="всг.", name="весьегонский", type=4, sorting=1)
        clear_italic_tag_cache()

    def tearDown(self):
        clear_italic_tag_cache()

    def test_highlights_known_italic_tags_only(self):
        src = (
            "<b>äbäreh</b> <i>s</i> негодник <i>(о детях)</i>; "
            "<i>перен.</i> озорник; <i>см.</i> lemma"
        )
        out = highlight_tags(src)
        self.assertIn('<i class="text-tag">s</i>', out)
        self.assertIn('<i class="text-tag">перен.</i>', out)
        self.assertIn("<i>(о детях)</i>", out)
        self.assertNotIn('class="text-tag">(о детях)', out)
        self.assertIn("<i>см.</i>", out)
        self.assertNotIn('class="text-tag">см.', out)

    def test_dialect_tag(self):
        self.assertIn('<i class="text-tag">всг.</i>', highlight_tags("<i>всг.</i> x"))

    def test_cache_reused_until_cleared(self):
        first = get_italic_tag_values()
        Tag.objects.create(tag="бранн.", name="бранное", type=3, sorting=2)
        # Tag save signal clears cache; next get reloads including new tag.
        self.assertIn("бранн.", get_italic_tag_values())
        self.assertIn("s", first)

    def test_format_pipeline_keeps_tag_color_over_rus(self):
        html = "<b>x</b> <i>s</i> <i>перен.</i> быстро"
        out = format_article_html(html)
        self.assertIn('<i class="text-tag">s</i>', out)
        self.assertIn('class="text-tag"', out)
        self.assertIn('class="text-rus"', out)
        self.assertIn("быстро", out)
