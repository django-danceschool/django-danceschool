# Give this app a custom verbose name to avoid confusion
from django.apps import AppConfig


class PaypalHereAppConfig(AppConfig):
    name = 'danceschool.payments.paypal_here'
    verbose_name = 'Paypal Here Point Of Sale Functions'
