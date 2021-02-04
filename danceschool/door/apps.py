from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DoorAppConfig(AppConfig):
    name = 'danceschool.door'
    verbose_name = _('Door registration and check-in')
