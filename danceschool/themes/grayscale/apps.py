# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class GrayScaleAppConfig(AppConfig):
    name = 'danceschool.themes.grayscale'
    verbose_name = _('Grayscale Theme')

    def ready(self):
        pass
