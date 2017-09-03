from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class PrivateLessonsConfig(AppConfig):
    name = 'private_lessons'
    verbose_name = _('Private Lessons Functions')

    from . import handlers
