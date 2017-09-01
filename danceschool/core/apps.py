# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class CoreAppConfig(AppConfig):
    name = 'danceschool.core'
    verbose_name = _('Core School Functions')

    def ready(self):
        # Ensure that signal handlers are loaded
        from . import handlers
