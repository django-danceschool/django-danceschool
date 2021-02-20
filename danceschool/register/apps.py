from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RegisterAppConfig(AppConfig):
    name = 'danceschool.register'
    verbose_name = _('Registration and check-in')
