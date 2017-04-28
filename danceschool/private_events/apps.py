# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class PrivateEventsAppConfig(AppConfig):
    name = 'danceschool.private_events'
    verbose_name = _('Private Events Functions')
