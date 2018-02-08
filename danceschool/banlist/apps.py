# Third Party Imports
# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class BanlistAppConfig(AppConfig):
    name = 'danceschool.banlist'
    verbose_name = _('Registration Ban List Functions')

    def ready(self):
        from . import handlers
