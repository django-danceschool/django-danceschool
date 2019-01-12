from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class BackupsAppConfig(AppConfig):
    name = 'danceschool.backups'
    verbose_name = _('Backups')
