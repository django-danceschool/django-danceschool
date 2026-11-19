# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig


class PaypalAppConfig(AppConfig):
    name = 'danceschool.payments.paypal'
    verbose_name = 'Paypal Functions'
