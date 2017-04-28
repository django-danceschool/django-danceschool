# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig


class PaypalAppConfig(AppConfig):
    name = 'danceschool.paypal'
    verbose_name = 'Paypal Functions'

    def ready(self):
        # This ensures that the signal receivers are loaded
        from . import handlers
