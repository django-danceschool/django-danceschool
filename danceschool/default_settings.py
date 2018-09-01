# This file contains default settings for the django-danceschool project.
# To load these settings, add the following line to your project's
# settings.py file, near the top:
#
#     from danceschool.default_settings import *
#
# All settings can then be overridden in settings.py as needed.

# This import allows Huey to use a SQLite backend
from huey.contrib.sqlitedb import SqliteHuey

import sys
from os import path

# Required for Django CMS.  Override in your own settings.py
LANGUAGES = [('en', 'English'), ]

# Override in settings.py to add your own templates, or override the
# defaults directly by placing templates with the same name in a
# custom app or your /templates/ folder.
CMS_TEMPLATES = [
    ('cms/admin_home.html', 'Administrative Function base template'),
    ('cms/home.html', 'Base Template, one column'),
    ('cms/frontpage.html', 'Front page template'),
    ('cms/twocolumn_leftsidebar.html', 'Two columns, sidebar at left'),
    ('cms/twocolumn_rightsidebar.html', 'Two columns, sidebar at right'),
]

# This just ensures that Django-allauth is used as an authentication
# backend.
AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
)

# Settings for Django-allauth to allow login by email address, to require email
# address on signup, and to require email verification before login.
ACCOUNT_AUTHENTICATION_METHOD = "username_email"
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_UNIQUE_EMAIL = True

# FOR EASY THUMBNAILS (RETINA SUPPORT)
THUMBNAIL_HIGH_RESOLUTION = True
THUMBNAIL_PROCESSORS = (
    'easy_thumbnails.processors.colorspace',
    'easy_thumbnails.processors.autocrop',
    'filer.thumbnail_processors.scale_and_crop_with_subject_location',
    'easy_thumbnails.processors.filters',
)

# FOR DJANGO-FILER
FILER_ENABLE_PERMISSIONS = True

# FOR CKEDITOR INSTALL
CKEDITOR_IMAGE_BACKEND = 'pillow'
CKEDITOR_SETTINGS = {
    'language': '',
    'toolbar_CMS': [
        {'name': 'basicstyles', 'items': ['Bold', 'Italic', 'Underline', '-', 'RemoveFormat']},
        {'name': 'clipboard', 'items': ['Cut', 'Copy', 'Paste', 'PasteText', '-', 'Undo', 'Redo']},
        {
            'name': 'paragraph',
            'items': ['NumberedList', 'BulletedList', '-', 'Outdent', 'Indent', '-', 'Blockquote', 'CreateDiv', '-',
                      'JustifyLeft', 'JustifyCenter', 'JustifyRight', 'JustifyBlock']
        },
        {'name': 'styles', 'items': ['Format']},
        '/',
        {'name': 'links', 'items': ['Link', 'Unlink', 'Anchor']},
        {'name': 'insert', 'items': ['FilerImage', 'Table', 'HorizontalRule', 'Smiley', 'Iframe']},
        {'name': 'tools', 'items': ['Maximize', 'ShowBlocks', 'Source']},
    ],
    'toolbar_HTMLField': [
        {'name': 'basicstyles', 'items': ['Bold', 'Italic', 'Underline', '-', 'RemoveFormat']},
        {'name': 'clipboard', 'items': ['Cut', 'Copy', 'Paste', 'PasteText', '-', 'Undo', 'Redo']},
        {
            'name': 'paragraph',
            'items': ['NumberedList', 'BulletedList', '-', 'Outdent', 'Indent', '-', 'Blockquote', 'CreateDiv', '-',
                      'JustifyLeft', 'JustifyCenter', 'JustifyRight', 'JustifyBlock']
        },
        {'name': 'styles', 'items': ['Format']},
        '/',
        {'name': 'links', 'items': ['Link', 'Unlink', 'Anchor']},
        {'name': 'insert', 'items': ['FilerImage', 'Table', 'HorizontalRule', 'Smiley', 'Iframe']},
        {'name': 'tools', 'items': ['Maximize', 'ShowBlocks', 'Source']},
    ],
    'skin': 'moono-lisa',
    'extraPlugins': ','.join(
        [
            # you extra plugins here
            'filerimage',
        ]),
    'removePlugins': 'image',
}

# These settings allow <iframe> elements to be used in CKEditor.  Override or remove them to
# disable this feature.
TEXT_ADDITIONAL_TAGS = ('iframe',)
TEXT_ADDITIONAL_ATTRIBUTES = ('scrolling', 'allowfullscreen', 'frameborder')

# For Huey task queue and scheduling.  By default, this project uses the SQLite
# backend for easy testing.  For production purposes, it is strongly recommended
# that you use Huey's Redis backend by copying the lines below and pasting them
# into your project's settings.py file.
HUEY = SqliteHuey(
    'danceschool',
    filename=path.join(
        path.dirname(
            path.abspath(
                getattr(sys.modules['__main__'], '__file__', path.dirname(__file__)),
            )
        ),
        'huey.sqlite3'
    )
)
# from huey import RedisHuey
# from redis import ConnectionPool
# pool = ConnectionPool(host='localhost', port=6379, max_connections=20)
# HUEY = RedisHuey('danceschool',connection_pool=pool)

# For Crispy forms Bootstrap templates
CRISPY_TEMPLATE_PACK = 'bootstrap4'
CRISPY_FAIL_SILENTLY = True

DJANGOCMS_FORMS_PLUGIN_MODULE = 'Forms'
DJANGOCMS_FORMS_TEMPLATES = (
    ('djangocms_forms/form_template/default.html', 'Default'),
    ('forms/djangocms_forms_crispy.html', 'Crispy Form (recommended)'),
)

# For optional themes, these settings ensure that header image plugins have sensible
# defaults, and that the PictureTemplatePlugin can't be used in places where it
# wouldn't make sense to do so.
CMS_PLACEHOLDER_CONF = {
    None: {
        'excluded_plugins': ['PictureSplashTemplatePlugin',],
    },
    'splash_image': {
        'name': 'Splash Background Image',
        'plugins': ['PictureSplashTemplatePlugin',],
        'excluded_plugins': [],
        'limits': {
            'global': 1,
        },
    },
    'splash_title': {
        'name': 'Front Page Title',
    },
    'splash_caption': {
        'name': 'Front Page Caption'
    },
    'splash_carousel': {
        'name': 'Splash Carousel',
        'plugins': ['Bootstrap4CarouselPlugin',],
        'excluded_plugins': [],
        'limits': {
            'Bootstrap4CarouselPlugin': 1,
        },
    },
}

# DJANGOCMS_PICTURE_TEMPLATES = []
DJANGOCMS_PICTURE_TEMPLATES = [
    ('splash_image', 'Front Page Splash Image'),
]
