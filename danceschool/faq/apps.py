from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FAQAppConfig(AppConfig):
    name = 'danceschool.faq'
    verbose_name = _('FAQs')
