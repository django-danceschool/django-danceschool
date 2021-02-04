# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BusinessFrontpageAppConfig(AppConfig):
    name = 'danceschool.themes.business_frontpage'
    verbose_name = _('Business Front Page Theme')
