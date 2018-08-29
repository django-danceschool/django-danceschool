# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class ThemeAppConfig(AppConfig):
    name = 'danceschool.themes'
    verbose_name = _('Theme Functions')
