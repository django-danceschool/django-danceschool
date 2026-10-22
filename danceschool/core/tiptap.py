'''
Server-side wiring for the django-danceschool YouTube Tiptap extension.

The extension itself lives in
static/djangocms_text/tiptap_plugins/danceschool.youtube.js and registers
itself with the Tiptap registry exposed by djangocms-text.  This module only
makes djangocms-text load the script, label and place the toolbar button, and
keep the resulting <iframe> through the HTML sanitizer.
'''
from django.utils.translation import gettext_lazy as _

SCRIPT = 'djangocms_text/tiptap_plugins/danceschool.youtube.js'
TOOLBAR_ITEM = 'Youtube'

IFRAME_ATTRIBUTES = {
    'src', 'width', 'height', 'frameborder', 'allow', 'allowfullscreen', 'title',
}


def _has_item(toolbar, name):
    return any(isinstance(group, list) and name in group for group in toolbar)


def register_youtube_extension():
    try:
        from djangocms_text.editors import (
            DEFAULT_EDITOR, DEFAULT_TOOLBAR_CMS, DEFAULT_TOOLBAR_HTMLField,
            register_toolbar_labels,
        )
        from djangocms_text.html import register_cleaner_attributes
    except ImportError:
        # djangocms-text is not installed or is too old to support dynamic
        # Tiptap extensions; nothing to do.
        return

    if SCRIPT not in DEFAULT_EDITOR.js:
        DEFAULT_EDITOR.js = (*DEFAULT_EDITOR.js, SCRIPT)

    for toolbar in (DEFAULT_TOOLBAR_CMS, DEFAULT_TOOLBAR_HTMLField):
        if not _has_item(toolbar, TOOLBAR_ITEM):
            toolbar.append([TOOLBAR_ITEM])

    register_toolbar_labels({TOOLBAR_ITEM: {'title': _('YouTube video')}})
    register_cleaner_attributes({'iframe': IFRAME_ATTRIBUTES})
