# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class StatsAppConfig(AppConfig):
    name = 'danceschool.stats'
    verbose_name = _('Stats Functions')
