from django.test import SimpleTestCase, override_settings
from django.contrib.staticfiles import finders

from djangocms_text.editors import (
    DEFAULT_EDITOR, DEFAULT_TOOLBAR_CMS, DEFAULT_TOOLBAR_HTMLField,
)
from djangocms_text.html import clean_html

from danceschool.core.tiptap import SCRIPT, TOOLBAR_ITEM


class YoutubeTiptapExtensionTest(SimpleTestCase):
    '''
    The YouTube embed extension for the Tiptap editor must be loaded by the
    editor, placed in the toolbars, and survive the HTML sanitizer.
    '''

    def test_script_registered_with_editor(self):
        self.assertIn(SCRIPT, DEFAULT_EDITOR.js)

    def test_script_is_findable_static_file(self):
        self.assertIsNotNone(finders.find(SCRIPT))

    def test_toolbar_item_added_once(self):
        for toolbar in (DEFAULT_TOOLBAR_CMS, DEFAULT_TOOLBAR_HTMLField):
            count = sum(
                1 for group in toolbar
                if isinstance(group, list) and TOOLBAR_ITEM in group
            )
            self.assertEqual(count, 1)

    def test_sanitizer_keeps_youtube_iframe(self):
        html = (
            '<iframe src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ" '
            'width="640" height="360" frameborder="0" allowfullscreen="true" '
            'referrerpolicy="strict-origin-when-cross-origin"></iframe>'
        )
        cleaned = clean_html(html)
        self.assertIn('<iframe', cleaned)
        # YouTube needs a referrer or it shows a player configuration error.
        self.assertIn('referrerpolicy="strict-origin-when-cross-origin"', cleaned)
        self.assertIn('youtube-nocookie.com/embed/dQw4w9WgXcQ', cleaned)

    def test_script_sets_referrer_policy_on_iframe(self):
        with open(finders.find(SCRIPT)) as f:
            source = f.read()
        self.assertIn("referrerpolicy: 'strict-origin-when-cross-origin'", source)

    def test_sanitizer_strips_script_and_javascript_src(self):
        cleaned = clean_html(
            '<script>alert(1)</script>'
            '<iframe src="javascript:alert(1)"></iframe>'
        )
        self.assertNotIn('<script', cleaned)
        self.assertNotIn('javascript:', cleaned)
